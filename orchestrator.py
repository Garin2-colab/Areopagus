from __future__ import annotations

import json
import base64
import os
import re
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import modal

APP_NAME = "areopagus"
VOLUME_NAME = "areopagus-data"
DATA_DIR = Path("/data")
HISTORY_PATH = DATA_DIR / "history.json"
SCHEMA_PATH = Path(__file__).resolve().parent / "example" / "exampleJson.json"

TURN_COUNT = 3
KEYWORD_COUNT = 5

GEMINI_MODEL = "gemini-3-flash"
RUNWAY_MODEL = "gpt_image_2"
RUNWAY_RATIO = "1920:1920"
RUNWAY_QUALITY = "high"
RUNWAY_API_BASE = "https://api.dev.runwayml.com"
GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta"

app = modal.App(APP_NAME)
data_volume = modal.Volume.from_name(VOLUME_NAME, create_if_missing=True)
image = (
    modal.Image.debian_slim(python_version="3.11")
)
secret = modal.Secret.from_dotenv()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_schema_template() -> dict[str, Any]:
    raw = SCHEMA_PATH.read_text(encoding="utf-8")
    raw = raw.replace("\ufeff", "").replace("\u00a0", " ")
    return json.loads(raw)


def load_history() -> dict[str, Any]:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not HISTORY_PATH.exists():
        return {
            "project": "Areopagus",
            "created_at": utc_now(),
            "updated_at": utc_now(),
            "turns": [],
            "graph": {
                "nodes": [],
                "edges": [],
            },
        }

    with HISTORY_PATH.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def save_history(history: dict[str, Any]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    history["updated_at"] = utc_now()
    with HISTORY_PATH.open("w", encoding="utf-8") as fh:
        json.dump(history, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    data_volume.commit()


def extract_json_object(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start != -1 and end != -1 and end > start:
            return json.loads(cleaned[start : end + 1])
        raise


def gemini_api_key() -> str:
    key = os.getenv("GOOGLE_API_KEY", "").strip()
    if not key:
        raise RuntimeError("GOOGLE_API_KEY is missing. Add it to .env before running the orchestrator.")
    return key


def runway_api_key() -> str:
    key = os.getenv("RUNWAYML_API_SECRET", "").strip()
    if not key:
        raise RuntimeError("RUNWAYML_API_SECRET is missing. Add it to .env before running the orchestrator.")
    return key


def gemini_generate(
    prompt_text: str,
    *,
    image_bytes: bytes | None = None,
    image_mime_type: str | None = None,
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

    request = urllib.request.Request(
        url=f"{GEMINI_API_BASE}/models/{GEMINI_MODEL}:generateContent?key={gemini_api_key()}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    with urllib.request.urlopen(request) as response:
        data = json.loads(response.read().decode("utf-8"))

    candidates = data.get("candidates", [])
    if not candidates:
        raise RuntimeError(f"Gemini returned no candidates: {data}")

    parts = candidates[0].get("content", {}).get("parts", [])
    text = "".join(part.get("text", "") for part in parts if isinstance(part, dict))
    if not text:
        raise RuntimeError(f"Gemini returned an empty response: {data}")

    return extract_json_object(text)


def runway_request(method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url=f"{RUNWAY_API_BASE}{path}",
        data=data,
        headers={
            "Authorization": f"Bearer {runway_api_key()}",
            "X-Runway-Version": "2024-11-06",
            "Content-Type": "application/json",
        },
        method=method,
    )

    with urllib.request.urlopen(request) as response:
        return json.loads(response.read().decode("utf-8"))


def runway_create_text_to_image(prompt_text: str) -> dict[str, Any]:
    return runway_request(
        "POST",
        "/v1/text_to_image",
        {
            "model": RUNWAY_MODEL,
            "promptText": prompt_text,
            "ratio": RUNWAY_RATIO,
            "quality": RUNWAY_QUALITY,
        },
    )


def runway_get_task(task_id: str) -> dict[str, Any]:
    return runway_request("GET", f"/v1/tasks/{task_id}")


def runway_wait_for_output(task: dict[str, Any], timeout_seconds: int = 600) -> dict[str, Any]:
    task_id = task.get("id") or task.get("taskId") or task.get("task_id")
    if not task_id:
        return task

    deadline = time.time() + timeout_seconds
    current = task

    while time.time() < deadline:
        status = str(current.get("status") or current.get("state") or "").upper()
        output = current.get("output")
        if output:
            return current

        if status in {"SUCCEEDED", "SUCCESS", "COMPLETED", "DONE", "FINISHED"}:
            return current
        if status in {"FAILED", "CANCELLED", "CANCELED", "ERROR"}:
            raise RuntimeError(f"Runway task failed: {current}")

        time.sleep(5)
        current = runway_get_task(str(task_id))

    raise TimeoutError(f"Timed out waiting for Runway task {task_id}")


def normalize_keyword(keyword: str) -> str:
    keyword = keyword.strip().lower()
    keyword = keyword.replace(" ", "-")
    keyword = re.sub(r"[^a-z0-9#-]", "", keyword)
    if not keyword.startswith("#"):
        keyword = f"#{keyword}"
    return keyword


def dedupe_keywords(keywords: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for keyword in keywords:
        normalized = normalize_keyword(keyword)
        if normalized and normalized not in seen:
            seen.add(normalized)
            result.append(normalized)
    return result[:KEYWORD_COUNT]


def prompt_theme(turn_index: int) -> str:
    themes = [
        "a ceremonial civic oracle suspended between steel and cloud",
        "a brutalist archive chamber where verdicts become architecture",
        "a luminous final tribunal with the feeling of a future ritual",
    ]
    return themes[min(max(turn_index - 1, 0), len(themes) - 1)]


def build_futurist_prompt(
    schema_template: dict[str, Any],
    turn_index: int,
    previous_turns: list[dict[str, Any]],
) -> dict[str, Any]:
    previous_summary = [
        {
            "turn": turn.get("turn"),
            "keywords": turn.get("keywords", []),
            "critique": turn.get("critique", ""),
        }
        for turn in previous_turns
    ]

    prompt = f"""
You are Agent 1, the Futurist for the Areopagus project.

Your job is to generate a single valid JSON object that will be sent to Runway as promptText.

Rules:
- Return JSON only. No markdown, no code fences, no commentary.
- Use the provided schema as the structural guide.
- Keep the existing top-level keys from the schema:
  scene_description, subject, attire, lighting_and_effects, environment,
  color_palette, style, camera.
- Add these top-level keys:
  turn, debate_context, keywords
- `keywords` must be exactly 5 hash-tagged strings.
- Make the image concept evolve across turns while preserving the Areopagus identity.
- The result should feel cinematic, architectural, and high consequence.

Schema template:
{json.dumps(schema_template, indent=2, ensure_ascii=False)}

Debate history:
{json.dumps(previous_summary, indent=2, ensure_ascii=False)}

Current turn:
{turn_index}

Concept direction:
{prompt_theme(turn_index)}
"""

    prompt_json = gemini_generate(prompt)
    prompt_json["turn"] = turn_index
    prompt_json["debate_context"] = previous_summary

    if "keywords" not in prompt_json or not isinstance(prompt_json["keywords"], list):
        prompt_json["keywords"] = [
            "#liminal",
            "#structural",
            "#juridical",
            "#mythic",
            "#future",
        ]

    prompt_json["keywords"] = dedupe_keywords(prompt_json["keywords"])
    if len(prompt_json["keywords"]) < KEYWORD_COUNT:
        fallback = [
            "#liminal",
            "#structural",
            "#juridical",
            "#mythic",
            "#future",
        ]
        prompt_json["keywords"] = dedupe_keywords(prompt_json["keywords"] + fallback)

    return prompt_json


def runway_image_url(task: Any) -> str:
    candidates: list[Any] = []

    if isinstance(task, dict):
        for key in ("image_url", "url", "output"):
            value = task.get(key)
            if value is not None:
                candidates.append(value)
    else:
        for attr in ("image_url", "url", "output"):
            value = getattr(task, attr, None)
            if value is not None:
                candidates.append(value)

        images = getattr(task, "images", None)
        if images:
            candidates.extend(images)

    for candidate in candidates:
        if isinstance(candidate, str) and candidate.startswith("http"):
            return candidate

        if isinstance(candidate, list) and candidate:
            first = candidate[0]
            if isinstance(first, str) and first.startswith("http"):
                return first
            if isinstance(first, dict):
                for key in ("image_url", "url"):
                    value = first.get(key)
                    if isinstance(value, str) and value.startswith("http"):
                        return value
            for attr in ("image_url", "url"):
                value = getattr(first, attr, None)
                if isinstance(value, str) and value.startswith("http"):
                    return value

        if isinstance(candidate, dict):
            for key in ("image_url", "url"):
                value = candidate.get(key)
                if isinstance(value, str) and value.startswith("http"):
                    return value

        for attr in ("image_url", "url"):
            value = getattr(candidate, attr, None)
            if isinstance(value, str) and value.startswith("http"):
                return value

    raise ValueError("Could not extract an image URL from the Runway task response.")


def fetch_image_bytes(image_url: str) -> tuple[bytes, str]:
    with urllib.request.urlopen(image_url) as response:
        content_type = response.headers.get_content_type() or "image/png"
        return response.read(), content_type


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
- `agreed_keywords` must contain exactly 5 hash-tagged strings.
- The keywords should be the strongest shared language between the prompt and the image.
- Be severe but useful. Focus on material fidelity, structure, atmosphere, and symbolic clarity.

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


def graph_nodes_for_turn(turn_record: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    turn_id = f"turn-{turn_record['turn']}"
    image_id = turn_record["image_id"]

    nodes = [
        {
            "id": turn_id,
            "type": "turn",
            "label": f"Turn {turn_record['turn']}",
            "created_at": turn_record["created_at"],
        },
        {
            "id": image_id,
            "type": "image",
            "label": image_id,
            "url": turn_record["image_url"],
        },
    ]

    for keyword in turn_record["keywords"]:
        nodes.append(
            {
                "id": f"{image_id}:{keyword}",
                "type": "keyword",
                "label": keyword,
            }
        )

    edges = [
        {
            "from": turn_id,
            "to": image_id,
            "relation": "generated_image",
        }
    ]

    for keyword in turn_record["keywords"]:
        edges.append(
            {
                "from": image_id,
                "to": f"{image_id}:{keyword}",
                "relation": "tagged_with",
            }
        )

    return nodes, edges


@app.function(
    image=image,
    volumes={"/data": data_volume},
    secrets=[secret],
    timeout=60 * 30,
)
def orchestrate() -> dict[str, Any]:
    schema_template = load_schema_template()
    history = load_history()

    previous_turns = history.get("turns", [])
    turn_outputs: list[dict[str, Any]] = []

    for turn_index in range(1, TURN_COUNT + 1):
        prompt_json = build_futurist_prompt(
            schema_template=schema_template,
            turn_index=turn_index,
            previous_turns=previous_turns,
        )

        prompt_text = json.dumps(prompt_json, ensure_ascii=False, indent=2)
        runway_task = runway_wait_for_output(runway_create_text_to_image(prompt_text))

        image_url = runway_image_url(runway_task)
        critique_json = critique_image(
            prompt_json=prompt_json,
            image_url=image_url,
        )

        final_keywords = reconcile_keywords(
            agent1_keywords=prompt_json.get("keywords", []),
            agent2_keywords=critique_json.get("agreed_keywords", []),
            prompt_json=prompt_json,
            critique_json=critique_json,
        )

        turn_record = {
            "turn": turn_index,
            "created_at": utc_now(),
            "prompt_json": prompt_json,
            "prompt_text": prompt_text,
            "image_id": f"turn-{turn_index}-image",
            "image_url": image_url,
            "critique": critique_json.get("critique", ""),
            "agent2": critique_json,
            "keywords": final_keywords,
            "knowledge_graph": {
                "image_id": f"turn-{turn_index}-image",
                "keyword_links": [
                    {
                        "keyword": keyword,
                        "image_id": f"turn-{turn_index}-image",
                    }
                    for keyword in final_keywords
                ],
            },
        }

        nodes, edges = graph_nodes_for_turn(turn_record)
        history.setdefault("turns", []).append(turn_record)
        history.setdefault("graph", {}).setdefault("nodes", []).extend(nodes)
        history.setdefault("graph", {}).setdefault("edges", []).extend(edges)
        save_history(history)

        turn_outputs.append(turn_record)
        previous_turns = history["turns"]

    return {
        "history_path": str(HISTORY_PATH),
        "turns_completed": len(turn_outputs),
        "latest_turn": turn_outputs[-1] if turn_outputs else None,
    }


@app.local_entrypoint()
def main() -> None:
    result = orchestrate.remote()
    print(json.dumps(result, indent=2, ensure_ascii=False))
