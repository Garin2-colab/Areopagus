import os
import json
import io
import urllib.request
import urllib.error
from typing import Any, Dict, List, Tuple

from models.base import BaseModel, register_model
from models.runway import stringify_prompt_value, extract_aspect_ratio

IDEOGRAM_API_BASE = "https://api.ideogram.ai/v1/ideogram-v4"


@register_model
class IdeogramModel(BaseModel):
    @property
    def model_name(self) -> str:
        return "ideogram_v4"

    @property
    def aliases(self) -> List[str]:
        return [
            "ideogram",
            "ideogram4",
            "ideogram_4",
            "ideogram-v4",
            "ideogram_v4_0",
        ]

    def get_canonical_name(self, name: str) -> str:
        return "ideogram_v4"

    def get_prompt_guidance_text(self, has_reference_image: bool) -> str:
        guidance = """
MODEL SPECIFIC GUIDANCE FOR IDEOGRAM V4:
- Ideogram V4 excels at text rendering, typography, and graphic design-quality images.
- Write rich, descriptive prompts; the model has built-in 'magic prompt' enhancement.
- When a reference image is available, the model will remix it with your prompt.
"""
        if has_reference_image:
            guidance += "- A reference image is available and will be used as the basis for remixing.\n"
        return guidance

    def get_prompt_rules_text(self, has_reference_image: bool, action: str = "Initiate") -> str:
        return """
- Do NOT use the '@ReferenceImage' tag or any style slot tags (like '@AgentRef1', '@AgentRef2') inside `scene_description` or anywhere in prompt text under any circumstances (as this model does not support them).
- Make the `scene_description` highly diverse and detailed. Ideogram V4 benefits from rich, natural language descriptions.
"""

    def get_prompt_suffix_text(self, has_reference_image: bool) -> str:
        return ""

    def post_process_prompt_json(self, prompt_json: Dict[str, Any]) -> Dict[str, Any]:
        from core import remove_reference_tags
        return remove_reference_tags(prompt_json)

    def _get_api_key(self) -> str:
        return os.environ.get("IDEOGRAM_API_KEY", "").strip()

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
        boundary = "----IdeogramBoundary" + os.urandom(8).hex()
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

    def ideogram_generate(self, prompt_text: str) -> dict[str, Any]:
        """Text-to-image via Ideogram V4 generate endpoint (synchronous)."""
        api_key = self._get_api_key()
        if not api_key:
            raise ValueError("IDEOGRAM_API_KEY is not set. Please add it to your .env file or Modal secrets.")

        body, content_type = self._multipart_encode({"text_prompt": prompt_text})

        request = urllib.request.Request(
            url=f"{IDEOGRAM_API_BASE}/generate",
            data=body,
            headers={
                "Api-Key": api_key,
                "Content-Type": content_type,
            },
            method="POST",
        )

        print(f"[ideogram] Sending generate request, prompt length={len(prompt_text)}", flush=True)

        from core.utils import urlopen_with_retry
        try:
            with urlopen_with_retry(request, timeout=180) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body_text = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
            raise RuntimeError(
                f"HTTP {exc.code} calling Ideogram generate: {exc.reason}. Response: {body_text or '<empty>'}"
            ) from None

    def ideogram_remix(
        self,
        prompt_text: str,
        image_bytes: bytes,
        image_mime_type: str = "image/png",
        image_weight: int | None = None,
    ) -> dict[str, Any]:
        """Image-to-image via Ideogram V4 remix endpoint (synchronous)."""
        api_key = self._get_api_key()
        if not api_key:
            raise ValueError("IDEOGRAM_API_KEY is not set. Please add it to your .env file or Modal secrets.")

        # Determine file extension from mime type
        ext_map = {
            "image/png": "input.png",
            "image/jpeg": "input.jpg",
            "image/webp": "input.webp",
        }
        filename = ext_map.get(image_mime_type, "input.png")

        fields: dict[str, str] = {"text_prompt": prompt_text}
        if image_weight is not None:
            fields["image_weight"] = str(image_weight)

        files = {"image": (filename, image_bytes, image_mime_type)}
        body, content_type = self._multipart_encode(fields, files)

        request = urllib.request.Request(
            url=f"{IDEOGRAM_API_BASE}/remix",
            data=body,
            headers={
                "Api-Key": api_key,
                "Content-Type": content_type,
            },
            method="POST",
        )

        print(f"[ideogram] Sending remix request, prompt length={len(prompt_text)}, image size={len(image_bytes)} bytes", flush=True)

        from core.utils import urlopen_with_retry
        try:
            with urlopen_with_retry(request, timeout=180) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body_text = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
            raise RuntimeError(
                f"HTTP {exc.code} calling Ideogram remix: {exc.reason}. Response: {body_text or '<empty>'}"
            ) from None

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
        # Build reference images using RunwayModel's helper
        from models.runway import RunwayModel
        runway_handler = RunwayModel()
        from core import load_history, fetch_image_bytes
        history = None
        try:
            history = load_history()
        except Exception:
            pass

        selected_id = assessment.get("selected_image_id", "")
        selected_turn = next(
            (t for t in recent_turns if t.get("image_id") == selected_id), None
        ) if recent_turns else None

        refs = runway_handler.build_runway_reference_images(
            agent,
            prompt_json=prompt_json,
            selected_turn=selected_turn,
            history=history,
            model="gpt_image_2",
        )

        prompt_text = self._build_prompt_text(prompt_json)
        print(f"[ideogram] Formatted prompt: {prompt_text[:200]}...", flush=True)

        # Try to use remix if we have reference images, otherwise use generate
        ref_image_bytes = None
        ref_image_mime = None
        if refs:
            # Try to download the first reference image for remix
            first_ref_url = refs[0].get("uri", "")
            if first_ref_url:
                try:
                    ref_image_bytes, ref_image_mime = fetch_image_bytes(first_ref_url)
                    print(f"[ideogram] Using remix with reference image from: {first_ref_url[:80]}...", flush=True)
                except Exception as e:
                    print(f"[ideogram] Failed to fetch reference image, falling back to generate: {e}", flush=True)

        if ref_image_bytes and ref_image_mime:
            # Use remix endpoint (image-to-image)
            result = self.ideogram_remix(
                prompt_text,
                ref_image_bytes,
                ref_image_mime,
                image_weight=50,  # balanced between prompt and reference
            )
        else:
            # Use generate endpoint (text-to-image)
            result = self.ideogram_generate(prompt_text)

        # Extract the image URL from response
        data = result.get("data", [])
        if not data or not isinstance(data, list):
            raise RuntimeError(f"Ideogram returned no data: {result}")

        raw_image_url = data[0].get("url", "")
        if not raw_image_url:
            raise RuntimeError(f"Ideogram returned no image URL: {data[0]}")

        # Use seed as a pseudo task ID
        task_id = f"ideogram-{data[0].get('seed', 'unknown')}"

        print(f"[ideogram] Generation complete: resolution={data[0].get('resolution')}, seed={data[0].get('seed')}", flush=True)

        return task_id, raw_image_url, prompt_text

    def save_media(
        self,
        raw_media_url: str,
        image_id: str,
        aspect_ratio: str,
    ) -> Dict[str, Any]:
        from core import save_webp_image
        return save_webp_image(raw_media_url, image_id)
