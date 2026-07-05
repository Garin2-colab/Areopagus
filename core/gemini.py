import base64
import json
import re
import urllib.request
import urllib.error
from typing import Any

from core.config import (
    GEMINI_MODEL,
    GEMINI_API_BASE,
    KEYWORD_COUNT,
)
from core.utils import (
    gemini_api_key,
    extract_json_object,
    dedupe_keywords,
    urlopen_with_retry,
)
from core.media import fetch_image_bytes

def gemini_generate(
    prompt_text: str,
    *,
    image_bytes: bytes | None = None,
    image_mime_type: str | None = None,
    extra_images: list[tuple[bytes, str]] | None = None,
    model: str = GEMINI_MODEL,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "contents": [
            {
                "role": "user",
                "parts": [{"text": prompt_text}],
            }
        ],
        "generationConfig": {
            "temperature": 0.7,
            "responseMimeType": "application/json",
        },
    }

    if image_bytes is not None:
        if not image_mime_type:
            image_mime_type = "image/png"
        payload["contents"][0]["parts"].append(
            {
                "inline_data": {
                    "mime_type": image_mime_type,
                    "data": base64.b64encode(image_bytes).decode("ascii"),
                }
            }
        )

    if extra_images:
        for img_bytes, img_mime in extra_images:
            if img_bytes:
                payload["contents"][0]["parts"].append(
                    {
                        "inline_data": {
                            "mime_type": img_mime or "image/png",
                            "data": base64.b64encode(img_bytes).decode("ascii"),
                        }
                    }
                )

    request = urllib.request.Request(
        url=f"{GEMINI_API_BASE}/models/{model}:generateContent?key={gemini_api_key()}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urlopen_with_retry(request) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
        raise RuntimeError(
            f"HTTP {exc.code} calling Gemini: {exc.reason}. Response: {body or '<empty>'}"
        ) from None

    candidates = data.get("candidates", [])
    if not candidates:
        raise RuntimeError(f"Gemini returned no candidates: {data}")

    parts = candidates[0].get("content", {}).get("parts", [])
    text = "".join(part.get("text", "") for part in parts if isinstance(part, dict))
    if not text:
        raise RuntimeError(f"Gemini returned an empty response: {data}")

    return extract_json_object(text)


def critique_image(
    prompt_json: dict[str, Any],
    image_url: str,
) -> dict[str, Any]:
    image_bytes, mime_type = fetch_image_bytes(image_url)

    critique_prompt = f"""
You are Agent 2, the Brutalist critic for the Areopagus project.

Analyze the image against the Futurist JSON prompt below.

Rules:
- Return JSON only. No markdown, no code fences, no commentary.
- `critique` must be exactly two sentences.
- `critique` should respond directly to Agent 1's `proposal` like a design review, not just summarize keywords.
- `agreed_keywords` must contain exactly 5 hash-tagged strings.
- The keywords should be the strongest shared language between the prompt and the image.
- Be precise but useful. Focus on material fidelity, structure, atmosphere, and symbolic clarity.

Prompt JSON:
{json.dumps(prompt_json, indent=2, ensure_ascii=False)}

Image URL:
{image_url}
"""

    critique_json = gemini_generate(
        critique_prompt,
        image_bytes=image_bytes,
        image_mime_type=mime_type,
    )
    critique_json.setdefault("critique", "")
    critique_json.setdefault("agreed_keywords", [])
    critique_json["agreed_keywords"] = dedupe_keywords(critique_json["agreed_keywords"])
    return critique_json


def reconcile_keywords(
    agent1_keywords: list[str],
    agent2_keywords: list[str],
    prompt_json: dict[str, Any],
    critique_json: dict[str, Any],
) -> list[str]:
    first = dedupe_keywords(agent1_keywords)
    second = dedupe_keywords(agent2_keywords)
    shared = [keyword for keyword in first if keyword in second]
    combined = dedupe_keywords(shared + first + second)

    if len(combined) >= KEYWORD_COUNT:
        return combined[:KEYWORD_COUNT]

    seed_terms = [
        prompt_json.get("style", {}).get("aesthetic", ""),
        prompt_json.get("scene_description", ""),
        critique_json.get("critique", ""),
    ]
    derived: list[str] = []
    for term in seed_terms:
        for token in re.findall(r"[A-Za-z][A-Za-z0-9-]+", term):
            derived.append(f"#{token.lower()}")

    return dedupe_keywords(
        combined
        + derived
        + [
            "#liminal",
            "#structural",
            "#ritual",
            "#oracle",
            "#architectural",
        ]
    )
