import os
import json
import time
import urllib.request
import urllib.error
from typing import Any, Dict, List, Tuple

from models.base import BaseModel, register_model
from models.runway import extract_aspect_ratio

@register_model
class SeedanceModel(BaseModel):
    @property
    def model_name(self) -> str:
        return "seedance"

    @property
    def aliases(self) -> List[str]:
        return ["seedance_v2", "seedance2", "seedance_2_fast"]

    def get_prompt_guidance_text(self, has_reference_image: bool) -> str:
        return ""

    def get_prompt_rules_text(self, has_reference_image: bool, action: str = "Initiate") -> str:
        return "\n- Do NOT use the '@ReferenceImage' tag or any style slot tags (like '@AgentRef1', '@AgentRef2') inside `scene_description` or anywhere in prompt text under any circumstances (as this model does not support them)."

    def post_process_prompt_json(self, prompt_json: Dict[str, Any]) -> Dict[str, Any]:
        from orchestrator import remove_reference_tags
        return remove_reference_tags(prompt_json)

    def _get_api_key(self) -> str:
        from orchestrator import kie_api_key
        return kie_api_key()

    def kie_request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        api_key = self._get_api_key()
        if not api_key:
            raise ValueError("KIE_API_KEY is not set. Please add it to your .env file or Modal secrets.")

        url = f"https://api.kie.ai{path}"
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        
        request = urllib.request.Request(
            url=url,
            data=data,
            headers={
                "Authorization": f"Bearer {api_key}",
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
                f"HTTP {exc.code} calling Kie API {path}: {exc.reason}. Response: {body or '<empty>'}"
            ) from None

    def poll_kie_task(self, task_id: str, max_wait: int = 600) -> dict[str, Any]:
        """Poll Kie API task recordInfo until status/state is 'success' or 'fail'."""
        time.sleep(15)
        elapsed = 15

        while elapsed < max_wait:
            task = self.kie_request("GET", f"/api/v1/jobs/recordInfo?taskId={task_id}")
            code = task.get("code")
            if code != 200:
                raise RuntimeError(f"Kie API query failed with code {code}: {task.get('message')}")
                
            data = task.get("data", {})
            state = str(data.get("state") or "").lower()
            print(f"[poll_kie_task] taskId={task_id} state={state} elapsed={elapsed}s", flush=True)
            
            if state == "success":
                return data
                
            if state in ("fail", "failed"):
                fail_code = data.get("failCode") or ""
                fail_msg = data.get("failMsg") or "Unknown failure"
                raise RuntimeError(f"Kie API Seedance task {task_id} failed: {fail_code} - {fail_msg}")
                
            polling_delay = 10
            time.sleep(polling_delay)
            elapsed += polling_delay
            
        raise RuntimeError(f"Kie API Seedance task {task_id} timed out after {max_wait}s")

    def get_closest_seedance_aspect_ratio(self, aspect_ratio_str: str | None) -> str:
        if not aspect_ratio_str:
            return "16:9"
            
        supported = {
            "1:1": 1.0,
            "4:3": 4.0 / 3.0,
            "3:4": 3.0 / 4.0,
            "16:9": 16.0 / 9.0,
            "9:16": 9.0 / 16.0,
            "21:9": 21.0 / 9.0,
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

        full_prompt = ""
        if action == "Initiate":
            full_prompt = prompt_json.get("scene_description", "").strip()

        if not full_prompt:
            full_prompt = "Generate a sequence of multiple shots to capture the essence of the scene"
        
        aspect_ratio = None
        if selected_turn and "image_webp" in selected_turn:
            webp_info = selected_turn["image_webp"]
            if isinstance(webp_info, dict) and "dimensions" in webp_info:
                dims = webp_info["dimensions"]
                if isinstance(dims, dict) and dims.get("width") and dims.get("height"):
                    aspect_ratio = self.get_closest_seedance_aspect_ratio(f"{dims['width']}:{dims['height']}")
                    print(f"[seedance] Using aspect ratio from reference image: {aspect_ratio} ({dims['width']}x{dims['height']})", flush=True)

        if not aspect_ratio:
            raw_ratio = extract_aspect_ratio(prompt_json)
            aspect_ratio = self.get_closest_seedance_aspect_ratio(raw_ratio)
            print(f"[seedance] Using aspect ratio from prompt: {aspect_ratio} (raw: {raw_ratio})", flush=True)
        
        reference_urls = []
        for ref in refs:
            uri = ref.get("uri")
            if uri:
                reference_urls.append(uri)
                
        payload = {
            "model": "bytedance/seedance-2-fast",
            "callBackUrl": "",
            "input": {
                "prompt": full_prompt,
                "reference_image_urls": reference_urls,
                "return_last_frame": False,
                "generate_audio": True,
                "resolution": "480p",
                "aspect_ratio": aspect_ratio,
                "duration": 12,
                "web_search": False
            }
        }
        
        print(f"[seedance] Creating task with prompt: '{full_prompt}' aspect_ratio={aspect_ratio} references={reference_urls}", flush=True)
        res = self.kie_request("POST", "/api/v1/jobs/createTask", payload)
        
        code = res.get("code")
        if code != 200:
            raise RuntimeError(f"Kie API createTask failed with code {code}: {res.get('msg')}")
            
        data = res.get("data", {})
        task_id = data.get("taskId")
        if not task_id:
            raise RuntimeError(f"No taskId returned from Kie API createTask response: {res}")
            
        print(f"[seedance] Task created: {task_id}. Polling...", flush=True)
        completed_task_data = self.poll_kie_task(task_id)
        
        result_json_str = completed_task_data.get("resultJson") or ""
        if not result_json_str:
            raise RuntimeError(f"Kie API Seedance task {task_id} completed but resultJson is empty.")
            
        try:
            result_data = json.loads(result_json_str)
            result_urls = result_data.get("resultUrls") or []
            if not result_urls:
                raise RuntimeError(f"resultUrls list is empty in resultJson: {result_json_str}")
            raw_video_url = result_urls[0]
        except Exception as exc:
            raise RuntimeError(f"Failed to parse Kie API resultJson: {result_json_str}. Error: {exc}")
            
        print(f"[seedance] Completed video URL: {raw_video_url}", flush=True)
        return task_id, raw_video_url, full_prompt

    def save_media(
        self,
        raw_media_url: str,
        image_id: str,
        aspect_ratio: str,
    ) -> Dict[str, Any]:
        from orchestrator import save_mp4_video
        closest_ratio = self.get_closest_seedance_aspect_ratio(aspect_ratio)
        return save_mp4_video(raw_media_url, image_id, aspect_ratio=closest_ratio)
