from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any

import modal

APP_NAME = "areopagus-api-ping"
GEMINI_MODEL = "gemini-2.5-flash"
GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta"
RUNWAY_API_BASE = "https://api.dev.runwayml.com"

app = modal.App(APP_NAME)
image = modal.Image.debian_slim(python_version="3.11")


def gemini_api_key() -> str:
    return os.environ["GOOGLE_API_KEY"].strip()


def runway_api_key() -> str:
    return os.environ["RUNWAYML_API_SECRET"].strip()


def userapi_key() -> str:
    return os.environ.get("USERAPI_API_KEY", "").strip()


def request_json(url: str, *, method: str = "GET", payload: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> dict[str, Any]:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url=url,
        data=data,
        method=method,
        headers={
            "Content-Type": "application/json",
            **(headers or {}),
        },
    )

    try:
        with urllib.request.urlopen(request) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
        raise RuntimeError(
            f"HTTP {exc.code} calling {url}: {exc.reason}. Response: {body or '<empty>'}"
        ) from None


def gemini_hello() -> str:
    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [{"text": "Hello"}],
            }
        ]
    }

    response = request_json(
        f"{GEMINI_API_BASE}/models/{GEMINI_MODEL}:generateContent?key={gemini_api_key()}",
        method="POST",
        payload=payload,
    )

    candidates = response.get("candidates", [])
    if not candidates:
        raise RuntimeError(f"Gemini returned no candidates: {response}")

    parts = candidates[0].get("content", {}).get("parts", [])
    message = "".join(part.get("text", "") for part in parts if isinstance(part, dict)).strip()
    if not message:
        raise RuntimeError(f"Gemini returned an empty response: {response}")

    return message


def runway_organization_balance() -> dict[str, Any]:
    return request_json(
        f"{RUNWAY_API_BASE}/v1/organization",
        headers={
            "Authorization": f"Bearer {runway_api_key()}",
            "X-Runway-Version": "2024-11-06",
        },
    )


def userapi_hello() -> dict[str, Any]:
    api_key = userapi_key()
    if not api_key:
        return {"error": "USERAPI_API_KEY environment variable is missing."}
    
    url = "https://api.userapi.ai/midjourney/v2/status?hash=invalid-hash-test"
    try:
        res = request_json(url, headers={"api-key": api_key})
        return {"status": "authenticated", "response": res}
    except Exception as exc:
        err_msg = str(exc)
        if "401" in err_msg or "403" in err_msg or "unauthorized" in err_msg.lower():
            raise RuntimeError(f"UserAPI unauthorized. Key prefix: {api_key[:5] if api_key else ''}... Error: {err_msg}")
        return {"status": "authenticated", "note": "Key is authenticated, returned expected error for dummy hash.", "error_details": err_msg}


def kie_key() -> str:
    return os.environ.get("KIE_API_KEY", "").strip() or os.environ.get("KIE_TOKEN", "").strip()


def kie_hello() -> dict[str, Any]:
    api_key = kie_key()
    if not api_key:
        return {"error": "KIE_API_KEY environment variable is missing."}
    
    url = "https://api.kie.ai/api/v1/jobs/recordInfo?taskId=invalid-task-id-test"
    try:
        res = request_json(url, headers={"Authorization": f"Bearer {api_key}"})
        return {"status": "authenticated", "response": res}
    except Exception as exc:
        err_msg = str(exc)
        if "401" in err_msg or "403" in err_msg or "unauthorized" in err_msg.lower():
            raise RuntimeError(f"Kie API unauthorized. Key prefix: {api_key[:5] if api_key else ''}... Error: {err_msg}")
        return {"status": "authenticated", "note": "Key is authenticated, returned expected error for dummy task.", "error_details": err_msg}


@app.function(
    image=image,
    secrets=[
        modal.Secret.from_name("google-api-secret"),
        modal.Secret.from_name("runway-secret"),
        modal.Secret.from_dotenv(),
    ],
    timeout=60 * 10,
)
def ping_apis() -> dict[str, Any]:
    result: dict[str, Any] = {}

    try:
        result["gemini_response"] = gemini_hello()
    except Exception as exc:  # pragma: no cover - surfaced to the caller
        result["gemini_error"] = str(exc)

    try:
        result["runway_organization"] = runway_organization_balance()
    except Exception as exc:  # pragma: no cover - surfaced to the caller
        result["runway_error"] = str(exc)

    try:
        result["userapi_status"] = userapi_hello()
    except Exception as exc:
        result["userapi_error"] = str(exc)

    try:
        result["kie_status"] = kie_hello()
    except Exception as exc:
        result["kie_error"] = str(exc)

    return result


@app.local_entrypoint()
def main() -> None:
    result = ping_apis.remote()
    print(json.dumps(result, indent=2, ensure_ascii=False))
