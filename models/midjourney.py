import os
import json
import time
import urllib.request
import urllib.error
from typing import Any, Dict, List, Tuple

from models.base import BaseModel, register_model
from models.runway import stringify_prompt_value, extract_aspect_ratio

RUNWAY_POLLING_DELAY_SECONDS = 5

@register_model
class MidjourneyModel(BaseModel):
    @property
    def model_name(self) -> str:
        return "midjourney"

    def _get_api_key(self) -> str:
        from orchestrator import userapi_api_key
        return userapi_api_key()

    def userapi_request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        api_key = self._get_api_key()
        if not api_key:
            raise ValueError("USERAPI_API_KEY is not set. Please add it to your .env file or Modal secrets.")

        url = f"https://api.userapi.ai{path}"
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        
        request = urllib.request.Request(
            url=url,
            data=data,
            headers={
                "api-key": api_key,
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
                f"HTTP {exc.code} calling UserAPI {path}: {exc.reason}. Response: {body or '<empty>'}"
            ) from None

    def poll_userapi_task(self, task_id: str, max_wait: int = 600) -> dict[str, Any]:
        """Poll UserAPI status endpoint until status is 'done'."""
        time.sleep(15)
        elapsed = 15

        while elapsed < max_wait:
            task = self.userapi_request("GET", f"/midjourney/v2/status?hash={task_id}")
            status = str(task.get("status") or "").lower()
            print(f"[poll_userapi_task] hash={task_id} status={status} progress={task.get('progress')}% elapsed={elapsed}s", flush=True)
            
            if status == "done":
                prefilter = task.get("prefilter_result")
                if prefilter and isinstance(prefilter, list) and len(prefilter) > 0:
                    raise RuntimeError(f"UserAPI Midjourney task {task_id} failed safety prefilter check: {prefilter}")
                return task
                
            if status in ("error", "failed", "cancel"):
                reason = task.get("status_reason") or "Unknown failure"
                raise RuntimeError(f"UserAPI Midjourney task {task_id} failed with status '{status}': {reason}")
                
            polling_delay = 10
            time.sleep(polling_delay)
            elapsed += polling_delay
            
        raise RuntimeError(f"UserAPI Midjourney task {task_id} timed out after {max_wait}s")

    def build_midjourney_prompt_text(self, prompt_json: dict[str, Any]) -> str:
        parts = []
        
        scene = stringify_prompt_value(prompt_json.get("scene_description", ""))
        if scene:
            parts.append(scene)
        
        subject = stringify_prompt_value(prompt_json.get("subject", {}))
        if subject:
            parts.append(subject)
            
        attire = stringify_prompt_value(prompt_json.get("attire", {}))
        if attire:
            parts.append(attire)
            
        lighting = stringify_prompt_value(prompt_json.get("lighting_and_effects", {}))
        if lighting:
            parts.append(lighting)
            
        env = stringify_prompt_value(prompt_json.get("environment", {}))
        if env:
            parts.append(env)
            
        colors = stringify_prompt_value(prompt_json.get("color_palette", {}))
        if colors:
            parts.append(colors)
            
        style = stringify_prompt_value(prompt_json.get("style", {}))
        if style:
            parts.append(style)
            
        camera = stringify_prompt_value(prompt_json.get("camera", {}))
        if camera:
            parts.append(camera)
            
        cleaned_parts = [p.strip() for p in parts if isinstance(p, str) and p.strip()]
        return ", ".join(cleaned_parts)

    def format_midjourney_prompt(
        self,
        prompt_json: dict[str, Any],
        reference_images: list[dict[str, Any]],
        action: str,
        agent: dict[str, Any] | None = None,
    ) -> str:
        raw_prompt = self.build_midjourney_prompt_text(prompt_json)
        
        img_refs = []
        sref_refs = []
        
        for ref in reference_images:
            uri = ref.get("uri")
            tag = ref.get("tag")
            if not uri:
                continue
            if action == "Pivot" and tag in ("ReferenceImage", "CurrentThread"):
                img_refs.append(uri)
            else:
                sref_refs.append(uri)
                
        if agent:
            # 1. Profile / prompt image from Setting
            prompt_img = agent.get("prompt_image") or agent.get("promptImage")
            if isinstance(prompt_img, str) and prompt_img.strip():
                url = prompt_img.strip()
                if url not in img_refs and url not in sref_refs:
                    sref_refs.append(url)
                    
            # 2. referenceImages from Setting
            agent_refs = agent.get("referenceImages") or agent.get("reference_images") or []
            if isinstance(agent_refs, str):
                agent_refs = [agent_refs]
            elif isinstance(agent_refs, dict):
                agent_refs = [agent_refs]
                
            if isinstance(agent_refs, list):
                for ref in agent_refs:
                    url = None
                    if isinstance(ref, str):
                        url = ref.strip()
                    elif isinstance(ref, dict):
                        url = ref.get("uri") or ref.get("url") or ref.get("image_url")
                        if url:
                            url = url.strip()
                    if url and url not in img_refs and url not in sref_refs:
                        sref_refs.append(url)
                        
        # Budget is 2000 characters total (Midjourney limit is 2200)
        other_parts = []
        if img_refs:
            other_parts.append(" ".join(img_refs))
        if sref_refs:
            other_parts.append(f"--sref {' '.join(sref_refs)}")
        ratio = extract_aspect_ratio(prompt_json)
        if ratio:
            other_parts.append(f"--ar {ratio}")
        if action == "Pivot":
            other_parts.append("--profile e45mt9k 48lvp9w 4hi6mui")
            
        other_len = len(" ".join(other_parts)) + 2  # +2 for padding spaces
        max_prompt_len = max(200, 2000 - other_len)
        
        if len(raw_prompt) > max_prompt_len:
            raw_prompt = raw_prompt[:max_prompt_len]
            # Try to cut at last comma or space
            last_comma = raw_prompt.rfind(",")
            if last_comma > max_prompt_len - 100:
                raw_prompt = raw_prompt[:last_comma]
            else:
                last_space = raw_prompt.rfind(" ")
                if last_space > max_prompt_len - 50:
                    raw_prompt = raw_prompt[:last_space]
            raw_prompt = raw_prompt.strip() + "..."
            
        parts = []
        if img_refs:
            parts.append(" ".join(img_refs))
        if raw_prompt:
            parts.append(raw_prompt)
        if sref_refs:
            parts.append(f"--sref {' '.join(sref_refs)}")
        if ratio:
            parts.append(f"--ar {ratio}")
        if action == "Pivot":
            parts.append("--profile e45mt9k 48lvp9w 4hi6mui")
            
        final_prompt = " ".join(parts).strip()
        print(f"[format_midjourney_prompt] Final prompt length: {len(final_prompt)}", flush=True)
        return final_prompt

    def midjourney_select_best_image(
        self,
        grid_url: str,
        grid_bytes: bytes,
        mime_type: str,
        agent: dict[str, Any],
        prompt_json: dict[str, Any],
        action: str,
    ) -> int:
        selection_prompt = f"""
You are the lead design curator and autonomous evaluator for the Areopagus creative workspace.
You are reviewing a 2x2 grid image generated by Midjourney.

Grid Layout:
- Top-Left quadrant: Option 1
- Top-Right quadrant: Option 2
- Bottom-Left quadrant: Option 3
- Bottom-Right quadrant: Option 4

Evaluate these four quadrants based on the active agent's creative profile, design proposal, and aesthetic direction.

Agent Stance & Worldview:
"{agent.get("persona", "A highly precise visual designer.")}"

Original Prompt Design Intent:
{json.dumps(prompt_json, indent=2, ensure_ascii=False)}

Action Type:
{action}

Determine which quadrant (1, 2, 3, or 4) most successfully realizes the design goals, composition structure, material fidelity, and mood of the prompt.

Return a JSON object containing:
- "choice": integer (1, 2, 3, or 4)
- "reasoning": 2-sentence explanation of why this option is superior to the others.

Return JSON only:
{{"choice": 1, "reasoning": "..."}}
"""
        from orchestrator import gemini_generate, GEMINI_MODEL
        try:
            res = gemini_generate(
                selection_prompt,
                image_bytes=grid_bytes,
                image_mime_type=mime_type,
                model=GEMINI_MODEL
            )
            choice = res.get("choice")
            reasoning = res.get("reasoning", "")
            print(f"[midjourney_select_best_image] Gemini selected choice={choice}. Reasoning: {reasoning}", flush=True)
            if isinstance(choice, (int, float)) and 1 <= int(choice) <= 4:
                return int(choice)
        except Exception as exc:
            print(f"[warning] Gemini image selection failed: {exc}. Defaulting to option 1.", flush=True)
            
        return 1

    def generate(
        self,
        prompt_json: Dict[str, Any],
        reference_images: List[Dict[str, Any]],
        action: str,
        agent: Dict[str, Any],
        turn_number: int,
        recent_turns: List[Dict[str, Any]],
        assessment: Dict[str, Any],
    ) -> Tuple[str, str, str]:
        # Formulate Runway references just to tag Midjourney srefs
        from models.runway import RunwayModel
        runway_handler = RunwayModel()
        from orchestrator import load_history
        history = None
        try:
            history = load_history()
        except Exception:
            pass

        selected_id = assessment.get("selected_image_id", "")
        selected_turn = next((t for t in recent_turns if t.get("image_id") == selected_id), None) if recent_turns else None

        refs = runway_handler.build_runway_reference_images(
            agent,
            prompt_json=prompt_json,
            selected_turn=selected_turn,
            history=history,
            model="gpt_image_2"
        )

        prompt_text = self.format_midjourney_prompt(prompt_json, refs, action, agent=agent)
        print(f"[midjourney] Formatted prompt: {prompt_text}", flush=True)
        
        res = self.userapi_request("POST", "/midjourney/v2/imagine", {"prompt": prompt_text})
        task_id = res.get("hash") or res.get("jobid") or res.get("jobId")
        if not task_id:
            raise RuntimeError(f"No hash returned from userapi.ai imagine call: {res}")
        print(f"[midjourney] Imagine task created: {task_id}", flush=True)
        
        completed_task = self.poll_userapi_task(task_id)
        grid_url = completed_task.get("result", {}).get("url")
        if not grid_url:
            grid_url = completed_task.get("result", {}).get("proxy_url")
        if not grid_url:
            raise RuntimeError(f"No image URL in UserAPI task result: {completed_task}")
        print(f"[midjourney] Completed grid URL: {grid_url}", flush=True)
        
        from orchestrator import fetch_image_bytes
        grid_bytes, mime_type = fetch_image_bytes(grid_url)
        choice = self.midjourney_select_best_image(grid_url, grid_bytes, mime_type, agent, prompt_json, action)
        print(f"[midjourney] Gemini selected quadrant: {choice}", flush=True)
        
        res_upscale = self.userapi_request("POST", "/midjourney/v2/upscale", {"hash": task_id, "choice": choice})
        upscale_task_id = res_upscale.get("hash") or res_upscale.get("jobid") or res_upscale.get("jobId")
        if not upscale_task_id:
            raise RuntimeError(f"No hash returned from userapi.ai upscale call: {res_upscale}")
        print(f"[midjourney] Upscale task created: {upscale_task_id}", flush=True)
        
        completed_upscale = self.poll_userapi_task(upscale_task_id)
        raw_image_url = completed_upscale.get("result", {}).get("url")
        if not raw_image_url:
            raw_image_url = completed_upscale.get("result", {}).get("proxy_url")
        if not raw_image_url:
            raise RuntimeError(f"No upscale image URL in UserAPI result: {completed_upscale}")
        print(f"[midjourney] Completed upscale URL: {raw_image_url}", flush=True)

        return upscale_task_id, raw_image_url, prompt_text

    def save_media(
        self,
        raw_media_url: str,
        image_id: str,
        aspect_ratio: str,
    ) -> Dict[str, Any]:
        from orchestrator import save_webp_image
        return save_webp_image(raw_media_url, image_id)
