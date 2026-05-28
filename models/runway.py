import json
import time
import urllib.request
import urllib.error
from typing import Any, Dict, List, Tuple

from models.base import BaseModel, register_model

# Constants from orchestrator settings
RUNWAY_API_BASE = "https://api.dev.runwayml.com"
RUNWAY_POLLING_DELAY_SECONDS = 5
RUNWAY_QUALITY = "high"

RUNWAY_RATIO_BY_MODEL = {
    "gpt_image_2": {
        "1:1": "1920:1920",
        "4:3": "1920:1440",
        "3:4": "1440:1920",
        "16:9": "2560:1440",
        "9:16": "1440:2560",
        "21:9": "3840:1648",
        "9:21": "1440:2560",
    },
    "gemini_image3_pro": {
        "1:1": "1024:1024",
        "4:3": "1024:768",
        "3:4": "768:1024",
        "16:9": "1024:576",
        "9:16": "576:1024",
    },
}

def stringify_prompt_value(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        parts = [stringify_prompt_value(item) for item in value]
        return ", ".join(p for p in parts if p)
    if isinstance(value, dict):
        parts = []
        for key, item in value.items():
            rendered = stringify_prompt_value(item)
            if rendered:
                parts.append(f"{key}: {rendered}")
        return "; ".join(parts)
    return ""

def extract_aspect_ratio(prompt_json: Any) -> str:
    if not isinstance(prompt_json, dict):
        return "1:1"
    ratio = None
    if "style" in prompt_json and isinstance(prompt_json["style"], dict):
        ratio = prompt_json["style"].get("aspect_ratio") or prompt_json["style"].get("ratio")
    if not ratio:
        ratio = prompt_json.get("aspect_ratio") or prompt_json.get("ratio")
    if not isinstance(ratio, str):
        return "1:1"
    ratio = ratio.strip().replace(" ", "")
    ratio = ratio.replace("x", ":").replace("-", ":")
    return ratio

@register_model
class RunwayModel(BaseModel):
    @property
    def model_name(self) -> str:
        return "gpt_image_2"

    @property
    def aliases(self) -> List[str]:
        return [
            "gptimage2",
            "gpt_image2",
            "gemini_image3_pro",
            "gemini_3_pro",
            "gemini3pro",
            "gemini_3pro"
        ]

    def get_canonical_name(self, name: str) -> str:
        model_key = str(name).strip().lower().replace("-", "_").replace(" ", "_")
        if "gemini" in model_key:
            return "gemini_image3_pro"
        return "gpt_image_2"

    def get_prompt_guidance_text(self, has_reference_image: bool) -> str:
        if has_reference_image:
            return "\nYou are shown your baseline style reference image (AgentPrompt) in the multimodal context. You can reference it in your prompt fields using the tag '@ReferenceImage' to maintain persona style consistency."
        return ""

    def get_prompt_rules_text(self, has_reference_image: bool, action: str = "Initiate") -> str:
        if not has_reference_image:
            return ""
        if action == "Pivot":
            return (
                "\n- If reference_image_id is NOT null, you MUST reference '@ReferenceImage' inside `scene_description`. If it is null, do NOT use the '@ReferenceImage' tag."
                "\n- If you want to reference another style slot (e.g. @AgentRef2) without making it the primary visual guide, you can use its tag anywhere in prompt text."
            )
        return (
            "\n- If reference_image_id is NOT null, you must reference '@ReferenceImage' inside `scene_description`. If it is null, do NOT use the '@ReferenceImage' tag."
            "\n- If you want to reference another style slot (e.g. @AgentRef2) without making it the primary visual guide, you can use its tag anywhere in prompt text."
        )

    def get_prompt_suffix_text(self, has_reference_image: bool) -> str:
        if has_reference_image:
            return "- If appropriate, reference '@ReferenceImage' in your prompt fields to anchor the style."
        return ""


    def _get_api_key(self) -> str:
        from orchestrator import runway_api_key
        return runway_api_key()

    def runway_request(self, method: str, path: str, payload: dict | None = None) -> dict:
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            url=f"{RUNWAY_API_BASE}{path}",
            data=data,
            headers={
                "Authorization": f"Bearer {self._get_api_key()}",
                "X-Runway-Version": "2024-11-06",
                "Content-Type": "application/json",
            },
            method=method,
        )
        try:
            with urllib.request.urlopen(request) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
            raise RuntimeError(
                f"HTTP {exc.code} calling Runway {path}: {exc.reason}. Response: {body or '<empty>'}"
            ) from None

    def runway_create_text_to_image(
        self,
        prompt_text: str,
        *,
        model: str = "gpt_image_2",
        reference_images: list[dict[str, Any]] | None = None,
        aspect_ratio: str | None = None,
    ) -> dict[str, Any]:
        max_len = 5000 if model in ("gpt_image_2", "gemini_image3_pro") else 950
        safe_prompt = prompt_text[:max_len]
        ratio_val = self.runway_ratio_for_model(model, aspect_ratio or "1:1")
        payload: dict[str, Any] = {
            "model": model,
            "promptText": safe_prompt,
            "ratio": ratio_val,
        }
        if "gemini" not in model.lower():
            payload["quality"] = RUNWAY_QUALITY
        if reference_images:
            payload["referenceImages"] = reference_images

        print(f"Sending to Runway: Model=[{model}], Ratio=[{ratio_val}] (Requested AspectRatio=[{aspect_ratio}]), PromptLength=[{len(safe_prompt)}]", flush=True)

        return self.runway_request(
            "POST",
            "/v1/text_to_image",
            payload,
        )

    def runway_get_task(self, task_id: str) -> dict[str, Any]:
        return self.runway_request("GET", f"/v1/tasks/{task_id}")

    def runway_ratio_for_model(self, model: str, aspect_ratio: str = "1:1") -> str:
        model_ratios = RUNWAY_RATIO_BY_MODEL.get(model)
        if model_ratios and aspect_ratio in model_ratios:
            return model_ratios[aspect_ratio]
        if model_ratios and "1:1" in model_ratios:
            return model_ratios["1:1"]
        return "1920:1920" if model == "gpt_image_2" else "1024:1024"

    def runway_reference_limit(self, model: str) -> int:
        return 14 if model == "gemini_image3_pro" else 16

    def build_runway_reference_images(
        self,
        agent: dict[str, Any],
        prompt_json: dict[str, Any] | None,
        selected_turn: dict[str, Any] | None,
        history: dict[str, Any] | None,
        model: str,
    ) -> list[dict[str, Any]]:
        references: list[dict[str, Any]] = []

        def add_reference(uri: Any, tag: str) -> None:
            if not isinstance(uri, str) or not uri.strip():
                return
            uri_str = uri.strip()
            if "get-image" in uri_str or "get_image" in uri_str:
                from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode
                try:
                    parsed = urlparse(uri_str)
                    query_params = dict(parse_qsl(parsed.query))
                    
                    if "id" in query_params:
                        id_val = query_params["id"]
                        if id_val.endswith(".webp"):
                            query_params["id"] = id_val[:-5] + ".png"
                    
                    query_params["ext"] = ".png"
                    uri_str = urlunparse((
                        parsed.scheme,
                        parsed.netloc,
                        parsed.path,
                        parsed.params,
                        urlencode(query_params),
                        parsed.fragment
                    ))
                except Exception:
                    pass
            references.append({"uri": uri_str, "tag": tag})

        ref_decision = None
        if prompt_json and isinstance(prompt_json, dict):
            ref_decision = prompt_json.get("reference_image_id")

        agent_refs = agent.get("referenceImages") or agent.get("reference_images") or []
        if isinstance(agent_refs, dict):
            agent_refs = [agent_refs]

        if ref_decision is not None:
            if ref_decision in ("selected", "CurrentThread", "ReferenceImage"):
                if selected_turn:
                    add_reference(selected_turn.get("image_url"), "ReferenceImage")
                    add_reference(selected_turn.get("image_url"), "CurrentThread")
            elif ref_decision in ("profile", "AgentPrompt"):
                prompt_img = agent.get("prompt_image") or agent.get("promptImage")
                if prompt_img:
                    add_reference(prompt_img, "ReferenceImage")
                    add_reference(prompt_img, "AgentPrompt")
            elif isinstance(ref_decision, str) and ref_decision.strip():
                matched_style = None
                if ref_decision.lower().startswith("agentref"):
                    try:
                        idx = int(ref_decision[8:]) - 1
                        if isinstance(agent_refs, list) and 0 <= idx < len(agent_refs):
                            ref_item = agent_refs[idx]
                            if isinstance(ref_item, str):
                                matched_style = ref_item
                            elif isinstance(ref_item, dict):
                                matched_style = ref_item.get("uri") or ref_item.get("url") or ref_item.get("image_url")
                    except Exception:
                        pass

                if matched_style:
                    add_reference(matched_style, "ReferenceImage")
                    add_reference(matched_style, ref_decision)
                else:
                    target_url = None
                    if history and isinstance(history.get("turns"), list):
                        for turn in history["turns"]:
                            if turn.get("image_id") == ref_decision:
                                target_url = turn.get("image_url")
                                break
                    if target_url:
                        add_reference(target_url, "ReferenceImage")
        else:
            if selected_turn:
                add_reference(selected_turn.get("image_url"), "ReferenceImage")
                add_reference(selected_turn.get("image_url"), "CurrentThread")
            
            prompt_img = agent.get("prompt_image") or agent.get("promptImage")
            if prompt_img:
                add_reference(prompt_img, "ReferenceImage")
                add_reference(prompt_img, "AgentPrompt")

        inspiration_id = None
        if prompt_json and isinstance(prompt_json, dict):
            inspiration_id = prompt_json.get("inspiration_image_id")
        if inspiration_id:
            target_url = None
            if history and isinstance(history.get("turns"), list):
                for turn in history["turns"]:
                    if turn.get("image_id") == inspiration_id:
                        target_url = turn.get("image_url")
                        break
            if target_url:
                add_reference(target_url, "InspirationRef")

        if isinstance(agent_refs, list):
            for index, reference in enumerate(agent_refs, start=1):
                if isinstance(reference, str):
                    add_reference(reference, f"AgentRef{index}")
                elif isinstance(reference, dict):
                    add_reference(
                        reference.get("uri") or reference.get("url") or reference.get("image_url"),
                        reference.get("tag") or f"AgentRef{index}",
                    )

        unique: list[dict[str, Any]] = []
        seen: set[str] = set()
        for reference in references:
            uri = reference["uri"]
            if uri in seen:
                continue
            seen.add(uri)
            unique.append(reference)

        return unique[:self.runway_reference_limit(model)]

    def format_prompt_reference_tags(self, reference_images: list[dict[str, Any]]) -> str:
        tags = [reference.get("tag") for reference in reference_images if isinstance(reference.get("tag"), str) and reference.get("tag")]
        return ", ".join(f"@{tag}" for tag in tags)

    def build_runway_prompt_text(
        self,
        prompt_json: dict[str, Any],
        *,
        model: str,
        reference_images: list[dict[str, Any]] | None = None,
    ) -> str:
        reference_images = reference_images or []
        reference_tags = self.format_prompt_reference_tags(reference_images)

        if model == "gemini_image3_pro":
            lines = [
                f"Scene: {stringify_prompt_value(prompt_json.get('scene_description', ''))}",
                f"Subject: {stringify_prompt_value(prompt_json.get('subject', {}))}",
                f"Attire: {stringify_prompt_value(prompt_json.get('attire', {}))}",
                f"Lighting and effects: {stringify_prompt_value(prompt_json.get('lighting_and_effects', {}))}",
                f"Environment: {stringify_prompt_value(prompt_json.get('environment', {}))}",
                f"Color palette: {stringify_prompt_value(prompt_json.get('color_palette', {}))}",
                f"Style: {stringify_prompt_value(prompt_json.get('style', {}))}",
                f"Camera: {stringify_prompt_value(prompt_json.get('camera', {}))}",
            ]
            prompt_str = "\n".join(line for line in lines if line)
            if len(prompt_str) > 5000:
                prompt_str = prompt_str[:5000]
            return prompt_str

        prompt_str = json.dumps(prompt_json, ensure_ascii=False, indent=2)
        if len(prompt_str) > 5000:
            prompt_str = prompt_str[:5000]
        return prompt_str

    def poll_runway_task(self, task_id: str, max_wait: int = 600) -> dict[str, Any]:
        start_time = time.time()
        while time.time() - start_time < max_wait:
            task = self.runway_get_task(task_id)
            status = task.get("status")
            print(f"Polling Runway Task [{task_id}]: Status=[{status}]", flush=True)
            if status == "SUCCEEDED":
                return task
            if status == "FAILED":
                raise RuntimeError(f"Runway Task failed: {task.get('failureCode') or 'Unknown error'}")
            time.sleep(RUNWAY_POLLING_DELAY_SECONDS)

        raise TimeoutError(f"Runway Task [{task_id}] did not complete within {max_wait} seconds.")

    def generate(
        self,
        prompt_json: Dict[str, Any],
        reference_images: List[Dict[str, Any]],
        action: str,
        agent: Dict[str, Any],
        turn_number: int,
        recent_turns: List[Dict[str, Any]],
        assessment: Dict[str, Any],
    ) -> Tuple[str, str]:
        # Determine model
        raw_model = agent.get("selected_model") or agent.get("model") or "gpt_image_2"
        model = str(raw_model).strip().lower().replace("-", "_").replace(" ", "_")
        canonical_model = "gemini_image3_pro" if "gemini" in model else "gpt_image_2"

        # Read history context if available from caller
        from orchestrator import load_history
        history = None
        try:
            history = load_history()
        except Exception:
            pass

        selected_id = assessment.get("selected_image_id", "")
        selected_turn = next((t for t in recent_turns if t.get("image_id") == selected_id), None) if recent_turns else None

        refs = self.build_runway_reference_images(
            agent,
            prompt_json=prompt_json,
            selected_turn=selected_turn,
            history=history,
            model=canonical_model
        )

        prompt_text = self.build_runway_prompt_text(
            prompt_json,
            model=canonical_model,
            reference_images=refs
        )

        aspect_ratio = extract_aspect_ratio(prompt_json)
        task = self.runway_create_text_to_image(
            prompt_text,
            model=canonical_model,
            reference_images=refs,
            aspect_ratio=aspect_ratio
        )
        task_id = task["id"]
        completed = self.poll_runway_task(task_id)

        # Get raw image URL
        raw_image_url = ""
        outputs = completed.get("output", [])
        if outputs and isinstance(outputs, list):
            raw_image_url = outputs[0]
        if not raw_image_url:
            raise RuntimeError(f"Runway task response has no output URL: {completed}")

        return task_id, raw_image_url, prompt_text

    def save_media(
        self,
        raw_media_url: str,
        image_id: str,
        aspect_ratio: str,
    ) -> Dict[str, Any]:
        from orchestrator import save_webp_image
        return save_webp_image(raw_media_url, image_id)
