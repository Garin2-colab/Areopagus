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

    def get_prompt_guidance_text(self, has_reference_image: bool) -> str:
        return """
MODEL SPECIFIC GUIDANCE FOR MIDJOURNEY:
- We want to generate highly diverse visual outputs. When writing the `scene_description`, do not follow a rigid template. Produce prompts of varying complexity:
  - Sometimes write a simple, direct 1-sentence prompt focusing on a single strong subject or action.
  - Sometimes write a highly abstract, symbolic, glitched, or conceptual prompt (e.g., glitched pixels, symbolic layouts, experimental textures).
  - Sometimes write a complex, multi-sentence hyper-detailed scenario detailing camera precision (e.g., Fujifilm GFX100, medium shots, extreme close-ups), specific environments (salt plains, concrete studio floors), and lighting details.
- To achieve a premium fashion/editorial look, incorporate references to famous visual artists, designers, photographers, or directors (e.g., in the style of Chen Man, Bruno Aveillan, Darren Aronofsky, Yoshitaka Amano, Tim Walker, Annie Leibovitz, Mert and Marcus, Iris van Herpen, Nick Knight, Alexander McQueen, Yohji Yamamoto, Chanel, etc.) to ground the aesthetic.
"""

    def get_prompt_rules_text(self, has_reference_image: bool, action: str = "Initiate") -> str:
        return """
- Do NOT use the '@ReferenceImage' tag or any style slot tags (like '@AgentRef1', '@AgentRef2') inside `scene_description` or anywhere in prompt text under any circumstances (as this model does not support them).
- Make the `scene_description` highly diverse: vary it between simple, abstract, and complex formats. Use names of famous designers/artists/photographers (e.g., Chen Man, Bruno Aveillan, Darren Aronofsky, Yoshitaka Amano, Tim Walker, Annie Leibovitz, Mert and Marcus, Nick Knight, Iris van Herpen, Alexander McQueen, Yohji Yamamoto, etc.) to establish a premium look and feel.
"""

    def post_process_prompt_json(self, prompt_json: Dict[str, Any]) -> Dict[str, Any]:
        from orchestrator import remove_reference_tags
        return remove_reference_tags(prompt_json)

    def _get_api_key(self) -> str:
        return os.environ.get("USERAPI_API_KEY", "").strip()

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
        
        def ensure_midjourney_image_extension(url: str) -> str:
            if not url:
                return url
            url = url.strip()
            if "s.mj.run" in url:
                return url
            
            from urllib.parse import urlparse, urlunparse, parse_qsl
            try:
                parsed = urlparse(url)
                path = parsed.path
                if not path:
                    path = "/"
                
                path_lower = path.lower()
                has_ext = any(path_lower.endswith(ext) or path_lower.endswith(ext + "/") for ext in (".webp", ".png", ".jpg", ".jpeg"))
                
                query = parsed.query
                if not has_ext:
                    q_params = dict(parse_qsl(query))
                    if "ext" not in q_params:
                        if query:
                            query += "&ext=.webp"
                        else:
                            query = "ext=.webp"
                
                return urlunparse((
                    parsed.scheme,
                    parsed.netloc,
                    path,
                    parsed.params,
                    query,
                    parsed.fragment
                ))
            except Exception:
                return url


        img_refs = []
        sref_refs = []
        
        for ref in reference_images:
            uri = ref.get("uri")
            tag = ref.get("tag")
            if not uri:
                continue
            uri = ensure_midjourney_image_extension(uri)
            if action == "Pivot" and tag in ("ReferenceImage", "CurrentThread"):
                img_refs.append(uri)
            else:
                sref_refs.append(uri)
                
        if agent:
            # 1. Profile / prompt image from Setting
            prompt_img = agent.get("prompt_image") or agent.get("promptImage")
            if isinstance(prompt_img, str) and prompt_img.strip():
                url = ensure_midjourney_image_extension(prompt_img.strip())
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
                    if url:
                        url = ensure_midjourney_image_extension(url)
                        if url not in img_refs and url not in sref_refs:
                            sref_refs.append(url)
                        
        import random
        ref_id = prompt_json.get("reference_image_id")
        if ref_id is not None or random.random() < 0.25:
            rand_sref = str(random.randint(100000000, 9999999999))
            if rand_sref not in sref_refs:
                sref_refs.append(rand_sref)

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
            other_parts.append("--w 500 --c 30")
            
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
            parts.append("--w 500 --c 30")
            
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

        return task_id, f"{grid_url}#{choice}", prompt_text

    def save_media(
        self,
        raw_media_url: str,
        image_id: str,
        aspect_ratio: str,
    ) -> Dict[str, Any]:
        from orchestrator import save_webp_image, fetch_image_bytes, IMAGE_DIR, WEBP_QUALITY, get_image
        from io import BytesIO
        from PIL import Image

        if "#" in raw_media_url:
            grid_url, choice = raw_media_url.split("#", 1)
            print(f"[midjourney] Slicing quadrant {choice} from grid image: {grid_url}", flush=True)
            try:
                grid_bytes, _ = fetch_image_bytes(grid_url)
                IMAGE_DIR.mkdir(parents=True, exist_ok=True)
                webp_path = IMAGE_DIR / f"{image_id}.webp"

                with Image.open(BytesIO(grid_bytes)) as img:
                    w, h = img.size
                    mid_x = w // 2
                    mid_y = h // 2

                    choice_str = str(choice).strip().upper()
                    if choice_str in ("U1", "1"):
                        box = (0, 0, mid_x, mid_y)
                    elif choice_str in ("U2", "2"):
                        box = (mid_x, 0, w, mid_y)
                    elif choice_str in ("U3", "3"):
                        box = (0, mid_y, mid_x, h)
                    elif choice_str in ("U4", "4"):
                        box = (mid_x, mid_y, w, h)
                    else:
                        box = (0, 0, w, h)

                    cropped = img.crop(box)
                    cw, ch = cropped.size
                    if cw > ch:
                        target_w = 1080
                        target_h = int(1080 * (ch / cw))
                    else:
                        target_h = 1080
                        target_w = int(1080 * (cw / ch))

                    converted = cropped.convert("RGB").resize((target_w, target_h), Image.Resampling.LANCZOS)
                    converted.save(webp_path, "WEBP", quality=WEBP_QUALITY, method=6)
                    width, height = converted.size

                try:
                    web_url = get_image.get_web_url()
                except Exception:
                    web_url = None

                if not web_url:
                    web_url = "https://heebok-lee--areopagus-get-image.modal.run"

                web_url = web_url.rstrip("/")

                return {
                    "path": str(webp_path),
                    "url": f"{web_url}/?id={image_id}",
                    "format": "webp",
                    "quality": WEBP_QUALITY,
                    "width": width,
                    "height": height,
                }
            except Exception as e:
                print(f"[midjourney] Error slicing grid image, falling back to full grid: {e}", flush=True)
                return save_webp_image(grid_url, image_id)

        return save_webp_image(raw_media_url, image_id)

