import os
import json
import time
import urllib.request
import urllib.error
from typing import Any, Dict, List, Tuple

from models.base import BaseModel, register_model
from models.runway import extract_aspect_ratio, stringify_prompt_value

@register_model
class KreaModel(BaseModel):
    @property
    def model_name(self) -> str:
        return "krea2"

    @property
    def aliases(self) -> List[str]:
        return [
            "krea2",
            "krea_2",
            "krea",
            "krea2_large",
            "krea_2_large",
            "krea2_medium",
            "krea_2_medium"
        ]

    def get_canonical_name(self, name: str) -> str:
        return "krea2"

    def get_prompt_guidance_text(self, has_reference_image: bool) -> str:
        guidance = """
MODEL SPECIFIC GUIDANCE FOR KREA 2:
- Krea 2 excels at artistic, expressive directions and creative control.
- Tunable creativity is supported (raw, low, medium, high).
- Style references can be uploaded and applied to generation requests.
"""
        if has_reference_image:
            guidance += "- A style reference is available and will be uploaded to Krea assets and applied.\n"
        return guidance

    def get_prompt_rules_text(self, has_reference_image: bool, action: str = "Initiate") -> str:
        return """
- Do NOT use the '@ReferenceImage' tag or any style slot tags (like '@AgentRef1', '@AgentRef2') inside `scene_description` or anywhere in prompt text under any circumstances.
- Write rich, visually detailed prompts to leverage Krea 2's high aesthetic diversity.
"""

    def get_prompt_suffix_text(self, has_reference_image: bool) -> str:
        return ""

    def post_process_prompt_json(self, prompt_json: Dict[str, Any]) -> Dict[str, Any]:
        from core import remove_reference_tags
        return remove_reference_tags(prompt_json)

    def _get_api_token(self) -> str:
        return os.environ.get("KREA_API_TOKEN", "").strip()

    def _build_prompt_text(self, prompt_json: dict[str, Any]) -> str:
        """Flatten the structured prompt JSON into a natural-language string."""
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

        cleaned = [p.strip() for p in parts if isinstance(p, str) and p.strip()]
        return ". ".join(cleaned)

    def _multipart_encode(
        self,
        fields: dict[str, str],
        files: dict[str, tuple[str, bytes, str]] | None = None,
    ) -> tuple[bytes, str]:
        """Build a multipart/form-data body manually (no extra deps)."""
        boundary = "----KreaBoundary" + os.urandom(8).hex()
        parts: list[bytes] = []

        for key, value in fields.items():
            parts.append(f"--{boundary}\r\n".encode())
            parts.append(f'Content-Disposition: form-data; name="{key}"\r\n\r\n'.encode())
            parts.append(value.encode("utf-8"))
            parts.append(b"\r\n")

        if files:
            for key, (filename, data, mime_type) in files.items():
                parts.append(f"--{boundary}\r\n".encode())
                parts.append(
                    f'Content-Disposition: form-data; name="{key}"; filename="{filename}"\r\n'.encode()
                )
                parts.append(f"Content-Type: {mime_type}\r\n\r\n".encode())
                parts.append(data)
                parts.append(b"\r\n")

        parts.append(f"--{boundary}--\r\n".encode())
        body = b"".join(parts)
        content_type = f"multipart/form-data; boundary={boundary}"
        return body, content_type

    def upload_asset(self, image_bytes: bytes, image_mime_type: str = "image/png") -> str:
        """Upload asset to Krea to get an image URL."""
        api_token = self._get_api_token()
        if not api_token:
            raise ValueError("KREA_API_TOKEN is not set. Please add it to your .env file or Modal secrets.")

        ext_map = {
            "image/png": "input.png",
            "image/jpeg": "input.jpg",
            "image/webp": "input.webp",
        }
        filename = ext_map.get(image_mime_type, "input.png")
        
        fields = {"description": "Style reference for Krea 2"}
        files = {"file": (filename, image_bytes, image_mime_type)}
        body, content_type = self._multipart_encode(fields, files)

        request = urllib.request.Request(
            url="https://api.krea.ai/assets",
            data=body,
            headers={
                "Authorization": f"Bearer {api_token}",
                "Content-Type": content_type,
            },
            method="POST",
        )

        from core.utils import urlopen_with_retry
        try:
            with urlopen_with_retry(request) as response:
                res = json.loads(response.read().decode("utf-8"))
                image_url = res.get("image_url")
                if not image_url:
                    raise RuntimeError(f"Krea asset upload did not return 'image_url': {res}")
                return image_url
        except urllib.error.HTTPError as exc:
            body_text = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
            raise RuntimeError(
                f"HTTP {exc.code} calling Krea asset upload: {exc.reason}. Response: {body_text or '<empty>'}"
            ) from None

    def krea_request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        api_token = self._get_api_token()
        if not api_token:
            raise ValueError("KREA_API_TOKEN is not set. Please add it to your .env file or Modal secrets.")

        url = f"https://api.krea.ai{path}"
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        
        req_headers = {
            "Authorization": f"Bearer {api_token}",
        }
        if payload is not None:
            req_headers["Content-Type"] = "application/json"
        if headers:
            req_headers.update(headers)

        request = urllib.request.Request(
            url=url,
            data=data,
            headers=req_headers,
            method=method,
        )

        from core.utils import urlopen_with_retry
        try:
            with urlopen_with_retry(request) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
            raise RuntimeError(
                f"HTTP {exc.code} calling Krea API {path}: {exc.reason}. Response: {body or '<empty>'}"
            ) from None

    def get_closest_krea_aspect_ratio(self, aspect_ratio_str: str | None) -> str:
        if not aspect_ratio_str:
            return "16:9"
            
        supported = {
            "1:1": 1.0,
            "4:3": 4.0 / 3.0,
            "3:2": 3.0 / 2.0,
            "16:9": 16.0 / 9.0,
            "2.35:1": 2.35,
            "4:5": 4.0 / 5.0,
            "2:3": 2.0 / 3.0,
            "9:16": 9.0 / 16.0,
        }
        
        try:
            parts = aspect_ratio_str.split(":")
            if len(parts) == 2:
                w, h = float(parts[0]), float(parts[1])
                ratio_num = w / h
            else:
                ratio_num = float(aspect_ratio_str)
        except Exception:
            return "16:9"
            
        closest = min(supported.keys(), key=lambda k: abs(supported[k] - ratio_num))
        return closest

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
        # Formulate Runway references first for consistency
        from models.runway import RunwayModel
        runway_handler = RunwayModel()
        from core import load_history, fetch_image_bytes
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

        prompt_text = self._build_prompt_text(prompt_json)
        print(f"[krea] Formatted prompt: {prompt_text[:200]}...", flush=True)

        # Upload references to Krea assets and build image_style_references
        image_style_references = []
        for ref in refs:
            uri = ref.get("uri")
            if uri:
                try:
                    print(f"[krea] Fetching and uploading reference image: {uri[:80]}...", flush=True)
                    ref_bytes, ref_mime = fetch_image_bytes(uri)
                    krea_style_url = self.upload_asset(ref_bytes, ref_mime)
                    image_style_references.append({
                        "url": krea_style_url,
                        "strength": 0.5
                    })
                except Exception as e:
                    print(f"[krea] Failed to upload reference image {uri}: {e}", flush=True)

        raw_ratio = extract_aspect_ratio(prompt_json)
        aspect_ratio = self.get_closest_krea_aspect_ratio(raw_ratio)
        print(f"[krea] Using aspect ratio: {aspect_ratio} (raw: {raw_ratio})", flush=True)

        payload = {
            "prompt": prompt_text,
            "aspect_ratio": aspect_ratio,
            "resolution": "1K",
            "creativity": "medium"
        }

        # Generative sliders default values (can be adjusted or left as default)
        payload["intensity"] = 0
        payload["complexity"] = 0
        payload["movement"] = 0

        if image_style_references:
            payload["image_style_references"] = image_style_references

        raw_model = agent.get("selected_model") or agent.get("model") or "krea2"
        model_str = str(raw_model).strip().lower()
        if "medium" in model_str:
            path = "/generate/image/krea/krea-2/medium"
        else:
            path = "/generate/image/krea/krea-2/large"

        print(f"[krea] Creating job via path: {path} with prompt: {prompt_text[:100]}...", flush=True)
        res = self.krea_request("POST", path, payload)
        
        job_id = res.get("job_id")
        if not job_id:
            raise RuntimeError(f"No job_id returned from Krea generate response: {res}")
            
        print(f"[krea] Job created: {job_id}. Polling...", flush=True)
        
        # Poll Krea API task
        time.sleep(2)
        elapsed = 2
        max_wait = 600
        while elapsed < max_wait:
            task = self.krea_request("GET", f"/jobs/{job_id}")
            status = str(task.get("status") or "").lower()
            print(f"[krea] Polling job_id={job_id} status={status} elapsed={elapsed}s", flush=True)
            
            if status == "completed":
                result_data = task.get("result", {})
                urls = result_data.get("urls") or []
                if not urls:
                    raise RuntimeError(f"Krea job {job_id} completed but urls list is empty.")
                raw_image_url = urls[0]
                return job_id, raw_image_url, prompt_text
                
            if status in ("failed", "cancelled"):
                error_msg = (
                    task.get("error") or 
                    task.get("result", {}).get("error") or 
                    task.get("message") or 
                    task.get("result", {}).get("message") or 
                    "Unknown error"
                )
                raise RuntimeError(f"Krea job {job_id} status is {status}: {error_msg}")
                
            polling_delay = 5
            time.sleep(polling_delay)
            elapsed += polling_delay

        raise RuntimeError(f"Krea job {job_id} timed out after {max_wait}s")

    def save_media(
        self,
        raw_media_url: str,
        image_id: str,
        aspect_ratio: str,
    ) -> Dict[str, Any]:
        from core import save_webp_image
        return save_webp_image(raw_media_url, image_id)
