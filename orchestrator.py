from __future__ import annotations

import json
import base64
import os
import re
import random
import time
import traceback
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import modal

APP_NAME = "areopagus"
VOLUME_NAME = "areopagus-data"
DATA_DIR = Path("/data")
HISTORY_PATH = DATA_DIR / "history.json"
AGENTS_CONFIG_PATH = DATA_DIR / "agents_config.json"
STUDIO_STATUS_PATH = DATA_DIR / "status.json"
HEARTBEAT_PATH = DATA_DIR / "last_heartbeat.json"
IMAGE_DIR = DATA_DIR / "images"
SCHEMA_PATH = Path(__file__).resolve().parent / "example" / "exampleJson.json"
ROOT_PATH = Path(__file__).resolve().parent
LOCAL_AGENTS_CONFIG_PATH = ROOT_PATH / "agents_config.json"

TURN_COUNT = 3
KEYWORD_COUNT = 5
RUNWAY_SAFETY_REPLACEMENTS = {
    "tribunal": "civic forum",
    "verdict": "annotation",
    "verdicts": "annotations",
    "judgment": "reflection",
    "judgement": "reflection",
    "punishment": "revision",
    "severe": "precise",
    "intense": "focused",
    "high consequence": "ceremonial",
    "nick knight": "editorial photography",
    "iris van herpen": "sculptural fashion",
    "dazed digital": "fashion publication",
    "vogue": "fashion magazine",
}

GEMINI_MODEL = "gemini-2.5-flash"
RUNWAY_MODEL = "gpt_image_2"
RUNWAY_GEMINI_IMAGE_MODEL = "gemini_image3_pro"
RUNWAY_ASPECT_RATIO = "1:1"
RUNWAY_RATIO_BY_MODEL = {
    "gpt_image_2": {
        "1:1": "1920:1920",
    },
    "gemini_image3_pro": {
        "1:1": "1024:1024",
    },
    "gen4_image": {
        "1:1": "1080:1080",
    },
    "gen4_image_turbo": {
        "1:1": "1080:1080",
    },
    "gemini_2.5_flash": {
        "1:1": "1024:1024",
    },
}
RUNWAY_QUALITY = "high"
WEBP_QUALITY = 60
RUNWAY_API_BASE = "https://api.dev.runwayml.com"
GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta"
INTEREST_WINDOW = 3
DEFAULT_AGENT_ACTIONS = {"Initiate", "Critique", "Pivot"}
PULSE_JITTER_MIN_SECONDS = 60
PULSE_JITTER_MAX_SECONDS = 120
RUNWAY_POLLING_DELAY_SECONDS = 5
CATEGORY_OPTIONS = [
    "Fashion",
    "Illustration",
    "Graphic Design",
    "Architecture",
    "UX/UI",
    "Industrial Design",
]

app = modal.App(APP_NAME)
data_volume = modal.Volume.from_name(VOLUME_NAME, create_if_missing=True)
image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install("pillow", "fastapi[standard]")
    .add_local_dir("./example", remote_path="/root/example")
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_schema_template() -> dict[str, Any]:
    raw = SCHEMA_PATH.read_text(encoding="utf-8")
    raw = raw.replace("\ufeff", "").replace("\u00a0", " ")
    return json.loads(raw)


def load_history() -> dict[str, Any]:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not HISTORY_PATH.exists():
        default_history = {
            "project": "Areopagus",
            "created_at": utc_now(),
            "updated_at": utc_now(),
            "turns": [],
            "threads": [],
            "graph": {
                "nodes": [],
                "edges": [],
            },
        }
        with HISTORY_PATH.open("w", encoding="utf-8") as fh:
            json.dump(default_history, fh, indent=2, ensure_ascii=False)
            fh.write("\n")
        data_volume.commit()
        return default_history

    with HISTORY_PATH.open("r", encoding="utf-8") as fh:
        history = json.load(fh)

    history.setdefault("turns", [])
    history.setdefault("threads", [])
    history.setdefault("graph", {"nodes": [], "edges": []})
    history["graph"].setdefault("nodes", [])
    history["graph"].setdefault("edges", [])
    return history


def load_agents_config(override: dict[str, Any] | None = None) -> dict[str, Any]:
    if isinstance(override, dict):
        override.setdefault("agents", [])
        return override

    for path in (AGENTS_CONFIG_PATH, LOCAL_AGENTS_CONFIG_PATH):
        if path.exists():
            with path.open("r", encoding="utf-8") as fh:
                config = json.load(fh)
            config.setdefault("agents", [])
            return config

    return {"agents": []}


def normalize_action(action: Any) -> str:
    if not isinstance(action, str):
        return "Critique"

    normalized = action.strip().title()
    if normalized in DEFAULT_AGENT_ACTIONS:
        return normalized
    return "Critique"


def get_active_agents(agents_config: dict[str, Any]) -> list[dict[str, Any]]:
    agents = agents_config.get("agents", [])
    if not isinstance(agents, list):
        return []

    active_agents: list[dict[str, Any]] = []
    for agent in agents:
        if not isinstance(agent, dict):
            continue

        active_value = agent.get("active", True)
        if isinstance(active_value, str):
            active = active_value.strip().lower() not in {"false", "0", "no", "off"}
        else:
            active = bool(active_value)

        if active:
            active_agents.append(agent)

    return active_agents


def summarize_turn_for_agent(turn: dict[str, Any]) -> dict[str, Any]:
    prompt_json = turn.get("prompt_json") if isinstance(turn.get("prompt_json"), dict) else {}
    return {
        "turn": turn.get("turn"),
        "image_id": turn.get("image_id"),
        "thread_id": turn.get("thread_id"),
        "proposal": turn.get("proposal", ""),
        "prompt": {
            "scene_description": prompt_json.get("scene_description", ""),
            "proposal": prompt_json.get("proposal", ""),
            "keywords": prompt_json.get("keywords", turn.get("keywords", [])),
        },
        "critique": turn.get("critique", ""),
        "keywords": turn.get("keywords", []),
        "action": turn.get("action"),
        "agent_id": turn.get("agent_id"),
    }


def recent_turns_for_agents(history: dict[str, Any], limit: int = INTEREST_WINDOW) -> list[dict[str, Any]]:
    turns = history.get("turns", [])
    if not isinstance(turns, list):
        return []
    return turns[-limit:]


def next_turn_number(history: dict[str, Any]) -> int:
    turns = history.get("turns", [])
    if not isinstance(turns, list) or not turns:
        return 1

    max_turn = 0
    for turn in turns:
        if isinstance(turn, dict):
            try:
                max_turn = max(max_turn, int(turn.get("turn", 0)))
            except (TypeError, ValueError):
                continue
    return max_turn + 1


def new_image_id(prefix: str, agent_id: str, turn_number: int) -> str:
    safe_agent_id = re.sub(r"[^a-zA-Z0-9_-]+", "-", agent_id).strip("-") or "agent"
    suffix = uuid.uuid4().hex[:8]
    return f"{prefix}-{safe_agent_id}-turn-{turn_number}-{suffix}"


def ensure_threads(history: dict[str, Any]) -> list[dict[str, Any]]:
    threads = history.setdefault("threads", [])
    if not threads:
        for turn in history.get("turns", []):
            if not isinstance(turn, dict):
                continue
            image_id = turn.get("image_id")
            if not image_id:
                continue
            threads.append(
                {
                    "thread_id": turn.get("thread_id") or image_id,
                    "root_image_id": turn.get("root_image_id") or image_id,
                    "title": f"Turn {turn.get('turn', '')}".strip(),
                    "active": True,
                    "posts": [image_id],
                    "comments": [],
                    "created_at": turn.get("created_at", utc_now()),
                    "updated_at": turn.get("created_at", utc_now()),
                }
            )
        save_history(history)

    return threads


def find_thread(history: dict[str, Any], thread_id: str) -> dict[str, Any] | None:
    for thread in ensure_threads(history):
        if thread.get("thread_id") == thread_id:
            return thread
    return None


def find_thread_for_image(history: dict[str, Any], image_id: str) -> dict[str, Any] | None:
    for thread in ensure_threads(history):
        if thread.get("root_image_id") == image_id or image_id in thread.get("posts", []):
            return thread
    return None


def upsert_thread(history: dict[str, Any], *, thread_id: str, root_image_id: str, title: str, agent_id: str, interest_score: int, action: str) -> dict[str, Any]:
    threads = ensure_threads(history)
    existing = find_thread(history, thread_id)
    if existing is None:
        existing = {
            "thread_id": thread_id,
            "root_image_id": root_image_id,
            "title": title,
            "agent_id": agent_id,
            "action": action,
            "interest_score": interest_score,
            "active": True,
            "posts": [root_image_id],
            "comments": [],
            "created_at": utc_now(),
            "updated_at": utc_now(),
        }
        threads.append(existing)
        return existing

    existing.setdefault("posts", [])
    if root_image_id not in existing["posts"]:
        existing["posts"].append(root_image_id)
    existing["title"] = title or existing.get("title", "")
    existing["agent_id"] = agent_id
    existing["action"] = action
    existing["interest_score"] = interest_score
    existing["updated_at"] = utc_now()
    return existing


def append_thread_comment(
    history: dict[str, Any],
    *,
    thread_id: str,
    comment: str,
    agent_id: str,
    agent_name: str,
    selected_image_id: str,
    interest_score: int,
) -> dict[str, Any]:
    thread = find_thread(history, thread_id)
    if thread is None:
        thread = upsert_thread(
            history,
            thread_id=thread_id,
            root_image_id=selected_image_id,
            title=f"Thread {selected_image_id}",
            agent_id=agent_id,
            interest_score=interest_score,
            action="Critique",
        )

    comment_record = {
        "id": f"comment-{uuid.uuid4().hex[:10]}",
        "agent_id": agent_id,
        "agent_name": agent_name,
        "post_image_id": selected_image_id,
        "comment": comment,
        "interest_score": interest_score,
        "created_at": utc_now(),
    }
    thread.setdefault("comments", []).append(comment_record)
    thread["updated_at"] = utc_now()
    return comment_record


def extract_first_string(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        for item in value:
            if isinstance(item, str):
                return item
    return ""


def prompt_payload_for_turn(turn: dict[str, Any]) -> dict[str, Any]:
    prompt_json = turn.get("prompt_json")
    if isinstance(prompt_json, dict):
        return prompt_json
    return {
        "scene_description": turn.get("proposal", ""),
        "proposal": turn.get("proposal", ""),
        "keywords": turn.get("keywords", []),
    }


def save_history(history: dict[str, Any]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    history["updated_at"] = utc_now()
    with HISTORY_PATH.open("w", encoding="utf-8") as fh:
        json.dump(history, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    data_volume.commit()


PENDING_TASKS_PATH = DATA_DIR / "pending_tasks.json"

def load_pending_tasks() -> dict[str, Any]:
    if not PENDING_TASKS_PATH.exists():
        return {}
    with PENDING_TASKS_PATH.open("r", encoding="utf-8") as fh:
        return json.load(fh)

def save_pending_task(task_data: dict[str, Any]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    tasks = load_pending_tasks()
    tasks[task_data["task_id"]] = task_data
    with PENDING_TASKS_PATH.open("w", encoding="utf-8") as fh:
        json.dump(tasks, fh, indent=2, ensure_ascii=False)
    data_volume.commit()

def remove_pending_task(task_id: str) -> dict[str, Any] | None:
    tasks = load_pending_tasks()
    task = tasks.pop(task_id, None)
    if task:
        with PENDING_TASKS_PATH.open("w", encoding="utf-8") as fh:
            json.dump(tasks, fh, indent=2, ensure_ascii=False)
        data_volume.commit()
    return task



def update_studio_status(message: str, active: bool = True, agent_name: str | None = None) -> dict[str, Any]:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    status = {
        "message": message,
        "active": active,
        "updated_at": utc_now(),
    }
    if agent_name:
        status["agent_name"] = agent_name
    with STUDIO_STATUS_PATH.open("w", encoding="utf-8") as fh:
        json.dump(status, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    data_volume.commit()
    return status


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
    return os.environ["GOOGLE_API_KEY"].strip()


def runway_api_key() -> str:
    return os.environ["RUNWAYML_API_SECRET"].strip()


def gemini_generate(
    prompt_text: str,
    *,
    image_bytes: bytes | None = None,
    image_mime_type: str | None = None,
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

    request = urllib.request.Request(
        url=f"{GEMINI_API_BASE}/models/{model}:generateContent?key={gemini_api_key()}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(request) as response:
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

    try:
        with urllib.request.urlopen(request) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
        raise RuntimeError(
            f"HTTP {exc.code} calling Runway {path}: {exc.reason}. Response: {body or '<empty>'}"
        ) from None


def runway_create_text_to_image(
    prompt_text: str,
    *,
    model: str = RUNWAY_MODEL,
    reference_images: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    # gpt_image_2 allows 32K chars, gemini_image3_pro allows 5.5K.
    # Use 5000 as a safe max that works for all models.
    max_len = 5000 if model in ("gpt_image_2", "gemini_image3_pro") else 950
    safe_prompt = prompt_text[:max_len]
    payload: dict[str, Any] = {
        "model": model,
        "promptText": safe_prompt,
        "ratio": runway_ratio_for_model(model),
    }
    if model != RUNWAY_GEMINI_IMAGE_MODEL:
        payload["quality"] = RUNWAY_QUALITY
    if reference_images:
        payload["referenceImages"] = reference_images

    print(f"Sending to Runway: Model=[{model}], PromptLength=[{len(safe_prompt)}]", flush=True)

    return runway_request(
        "POST",
        "/v1/text_to_image",
        payload,
    )


def runway_get_task(task_id: str) -> dict[str, Any]:
    return runway_request("GET", f"/v1/tasks/{task_id}")


def is_runway_safety_failure(exc: Exception) -> bool:
    message = str(exc).lower()
    return "safety" in message or "moderation" in message or "input_preprocessing" in message


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
        "a monumental archive chamber where annotations become architecture",
        "a luminous civic forum with the feeling of a future ritual",
    ]
    return themes[min(max(turn_index - 1, 0), len(themes) - 1)]


def sanitize_for_runway(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: sanitize_for_runway(item) for key, item in value.items()}

    if isinstance(value, list):
        return [sanitize_for_runway(item) for item in value]

    if isinstance(value, str):
        text = value
        for unsafe, replacement in RUNWAY_SAFETY_REPLACEMENTS.items():
            text = re.sub(rf"\b{re.escape(unsafe)}\b", replacement, text, flags=re.IGNORECASE)
        return text

    return value


def build_futurist_prompt(
    schema_template: dict[str, Any],
    turn_index: int,
    previous_turns: list[dict[str, Any]],
) -> dict[str, Any]:
    previous_summary = [
        {
            "turn": turn.get("turn"),
            "proposal": turn.get("proposal", ""),
            "keywords": turn.get("keywords", []),
            "critique": turn.get("critique", ""),
        }
        for turn in previous_turns
    ]

    safe_schema_template = sanitize_for_runway(schema_template)

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
  turn, debate_context, proposal, keywords
- `proposal` must be 2 to 3 sentences written as Agent 1's design review proposal.
- The proposal should explain the design intent, composition, material choices, and what Agent 2 should evaluate.
- `keywords` must be exactly 5 hash-tagged strings.
- Make the image concept evolve across turns while preserving the Areopagus identity.
- The result should feel cinematic, architectural, ceremonial, and non-violent.
- Avoid legal punishment, violence, threat, weapons, injury, gore, coercion, crime, detention, or execution language.
- Prefer neutral art-direction words such as civic forum, archive, annotation, reflection, assembly, ritual, structure, and studio.

Schema template:
{json.dumps(safe_schema_template, indent=2, ensure_ascii=False)}

Debate history:
{json.dumps(previous_summary, indent=2, ensure_ascii=False)}

Current turn:
{turn_index}

Concept direction:
{prompt_theme(turn_index)}
"""

    prompt_json = gemini_generate(prompt)
    prompt_json = sanitize_for_runway(prompt_json)
    prompt_json["turn"] = turn_index
    prompt_json["debate_context"] = sanitize_for_runway(previous_summary)
    if not isinstance(prompt_json.get("proposal"), str) or not prompt_json["proposal"].strip():
        prompt_json["proposal"] = (
            "Agent 1 proposes a civic image system where architecture, atmosphere, and ritual structure are held in balance. "
            "Agent 2 should evaluate whether the composition reads clearly as an Areopagus design review object."
        )

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
    try:
        with urllib.request.urlopen(image_url) as response:
            content_type = response.headers.get_content_type() or "image/png"
            return response.read(), content_type
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
        raise RuntimeError(
            f"HTTP {exc.code} fetching image {image_url}: {exc.reason}. Response: {body or '<empty>'}"
        ) from None


def save_webp_image(image_url: str, image_id: str) -> dict[str, Any]:
    from io import BytesIO

    from PIL import Image, ImageOps

    image_bytes, source_mime_type = fetch_image_bytes(image_url)
    IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    webp_path = IMAGE_DIR / f"{image_id}.webp"

    with Image.open(BytesIO(image_bytes)) as source:
        converted = ImageOps.fit(source.convert("RGB"), (1080, 1080), method=Image.Resampling.LANCZOS)
        converted.save(webp_path, "WEBP", quality=WEBP_QUALITY, method=6)
        width, height = converted.size

    return {
        "path": str(webp_path),
        "url": f"https://heebok-lee--areopagus-get-image.modal.run/?id={image_id}",
        "format": "webp",
        "quality": WEBP_QUALITY,
        "source_mime_type": source_mime_type,
        "size_bytes": webp_path.stat().st_size,
        "dimensions": {
            "width": width,
            "height": height,
        },
    }


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


def agent_gemini_model(agent: dict[str, Any]) -> str:
    gemini_model = agent.get("gemini_model")
    if isinstance(gemini_model, str) and gemini_model.strip():
        return gemini_model.strip()

    model_name = str(agent.get("model", "")).strip().lower()
    if "gemini" in model_name:
        return "gemini-2.5-flash"

    return GEMINI_MODEL


def agent_runway_model(agent: dict[str, Any]) -> str:
    raw_model = agent.get("selected_model") or agent.get("model") or RUNWAY_MODEL
    model = str(raw_model).strip().lower().replace("-", "_").replace(" ", "_")

    aliases = {
        "gpt_image_2": "gpt_image_2",
        "gptimage2": "gpt_image_2",
        "gpt_image2": "gpt_image_2",
        "gemini_image3_pro": "gemini_image3_pro",
        "gemini_3_pro": "gemini_image3_pro",
        "gemini3pro": "gemini_image3_pro",
        "gemini_3pro": "gemini_image3_pro",
        "gen4_image": "gen4_image",
        "gen4_image_turbo": "gen4_image_turbo",
        "gemini_2.5_flash": "gemini_2.5_flash",
    }

    if model in aliases:
        return aliases[model]

    return str(raw_model).strip()


def runway_ratio_for_model(model: str, aspect_ratio: str = RUNWAY_ASPECT_RATIO) -> str:
    model_ratios = RUNWAY_RATIO_BY_MODEL.get(model)
    if model_ratios and aspect_ratio in model_ratios:
        return model_ratios[aspect_ratio]

    return RUNWAY_RATIO_BY_MODEL[RUNWAY_MODEL][aspect_ratio]


def runway_reference_limit(model: str) -> int:
    return 14 if model == RUNWAY_GEMINI_IMAGE_MODEL else 16


def build_runway_reference_images(
    agent: dict[str, Any],
    *,
    selected_turn: dict[str, Any] | None = None,
    model: str = RUNWAY_MODEL,
) -> list[dict[str, Any]]:
    references: list[dict[str, Any]] = []

    def add_reference(uri: Any, tag: str) -> None:
        if not isinstance(uri, str) or not uri.strip():
            return
        references.append({"uri": uri.strip(), "tag": tag})

    agent_references = agent.get("referenceImages") or agent.get("reference_images") or []
    if isinstance(agent_references, dict):
        agent_references = [agent_references]
    if isinstance(agent_references, list):
        for index, reference in enumerate(agent_references, start=1):
            if isinstance(reference, str):
                add_reference(reference, f"AgentRef{index}")
            elif isinstance(reference, dict):
                add_reference(
                    reference.get("uri") or reference.get("url") or reference.get("image_url"),
                    reference.get("tag") or f"AgentRef{index}",
                )

    add_reference(agent.get("prompt_image") or agent.get("promptImage"), "AgentPrompt")

    if selected_turn is not None:
        add_reference(selected_turn.get("image_url"), "CurrentThread")

    unique: list[dict[str, Any]] = []
    seen: set[str] = set()
    for reference in references:
        uri = reference["uri"]
        if uri in seen:
            continue
        seen.add(uri)
        unique.append(reference)

    return unique[:runway_reference_limit(model)]


def format_prompt_reference_tags(reference_images: list[dict[str, Any]]) -> str:
    tags = [reference.get("tag") for reference in reference_images if isinstance(reference.get("tag"), str) and reference.get("tag")]
    return ", ".join(f"@{tag}" for tag in tags)


def stringify_prompt_value(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        parts = [stringify_prompt_value(item) for item in value]
        return ", ".join(part for part in parts if part)
    if isinstance(value, dict):
        parts: list[str] = []
        for key, item in value.items():
            rendered = stringify_prompt_value(item)
            if rendered:
                parts.append(f"{key}: {rendered}")
        return "; ".join(parts)
    return ""


def build_runway_prompt_text(
    prompt_json: dict[str, Any],
    *,
    model: str,
    agent: dict[str, Any],
    assessment: dict[str, Any],
    recent_turns: list[dict[str, Any]],
    action: str,
    selected_turn: dict[str, Any] | None = None,
    reference_images: list[dict[str, Any]] | None = None,
) -> str:
    reference_images = reference_images or []
    reference_tags = format_prompt_reference_tags(reference_images)

    if model == RUNWAY_GEMINI_IMAGE_MODEL:
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


def clamp_interest_score(value: Any) -> int:
    try:
        score = int(round(float(value)))
    except (TypeError, ValueError):
        score = 0
    return max(0, min(100, score))


def assess_agent_interest(agent: dict[str, Any], recent_turns: list[dict[str, Any]]) -> dict[str, Any]:
    prompt = f"""
You are the autonomous decision engine for Areopagus.

Return JSON only with this shape:
{{
  "agent_id": "...",
  "agent_name": "...",
  "initiate_score": 0,
  "initiate_reason": "...",
  "post_scores": [
    {{
      "turn": 0,
      "image_id": "...",
      "interest_score": 0,
      "action": "Critique",
      "reason": "..."
    }}
  ]
}}

Agent profile:
{json.dumps({
    "id": agent.get("id"),
    "name": agent.get("name"),
    "active": agent.get("active", True),
    "persona": agent.get("persona", ""),
    "model": agent.get("model", ""),
}, indent=2, ensure_ascii=False)}

Recent posts:
{json.dumps([summarize_turn_for_agent(turn) for turn in recent_turns], indent=2, ensure_ascii=False)}

Rules:
- You must decide how much this agent wants to start a completely new topic vs interact with existing posts.
- Give an `initiate_score` from 0 to 100 based strictly on the agent's persona. If the persona describes they love to generate new stuff, create their own posts, or initiate, this score should be very high (e.g., 80-100).
- For each of the recent posts, give an `interest_score` from 0 to 100. If the post perfectly aligns with the agent's persona and they have strong opinions on it, score it high.
- For each post, decide the best reply `action` if the agent were to reply:
  - Use `Pivot` when the agent wants to reply by generating a new image inspired by the post.
  - Use `Critique` when the agent wants to reply with text only (commenting).
- Keep reasons short and operational.
"""

    assessment = gemini_generate(prompt, model=agent_gemini_model(agent))
    assessment["agent_id"] = agent.get("id")
    assessment["agent_name"] = agent.get("name", agent.get("id", "Agent"))
    initiate_score = clamp_interest_score(assessment.get("initiate_score"))

    post_scores = assessment.get("post_scores", [])
    if not isinstance(post_scores, list):
        post_scores = []

    normalized_scores: list[dict[str, Any]] = []
    for score in post_scores:
        if not isinstance(score, dict):
            continue
        normalized_scores.append(
            {
                "turn": score.get("turn"),
                "image_id": score.get("image_id"),
                "interest_score": clamp_interest_score(score.get("interest_score")),
                "action": normalize_action(score.get("action")),
                "reason": score.get("reason", ""),
            }
        )

    best_post_score = max(normalized_scores, key=lambda item: item["interest_score"]) if normalized_scores else None

    if best_post_score and best_post_score["interest_score"] > initiate_score:
        assessment["selected_turn"] = best_post_score.get("turn")
        assessment["selected_image_id"] = best_post_score.get("image_id")
        assessment["interest_score"] = best_post_score["interest_score"]
        assessment["action"] = best_post_score["action"]
        assessment["reason"] = best_post_score.get("reason", "")
    else:
        assessment["selected_turn"] = None
        assessment["selected_image_id"] = ""
        assessment["interest_score"] = initiate_score
        assessment["action"] = "Initiate"
        assessment["reason"] = assessment.get("initiate_reason", "Agent persona prefers initiating a new thread.")

    assessment["post_scores"] = normalized_scores
    return assessment


def build_initiate_prompt_json(
    agent: dict[str, Any],
    recent_turns: list[dict[str, Any]],
    assessment: dict[str, Any],
    schema_template: dict[str, Any],
    turn_number: int,
) -> dict[str, Any]:
    prompt = f"""
You are drafting a brand-new Areopagus thread.

Return JSON only. Use the schema template below as the structural guide, then expand it into a fresh prompt that feels like a new thread rather than a revision.

Agent profile:
{json.dumps({
    "id": agent.get("id"),
    "name": agent.get("name"),
    "persona": agent.get("persona", ""),
    "model": agent.get("model", ""),
}, indent=2, ensure_ascii=False)}

Interest assessment:
{json.dumps(assessment, indent=2, ensure_ascii=False)}

Recent posts:
{json.dumps([summarize_turn_for_agent(turn) for turn in recent_turns], indent=2, ensure_ascii=False)}

Schema template:
{json.dumps(sanitize_for_runway(schema_template), indent=2, ensure_ascii=False)}

Rules:
- Keep the same top-level keys from the schema template.
- Add turn, debate_context, proposal, and keywords.
- proposal should be 2 to 3 sentences and should explain the design move the agent is initiating.
- keywords must be exactly 5 hash-tagged strings.
- The output should feel cinematic, architectural, ceremonial, and specific to the active agent persona.
- Return JSON only.
"""

    prompt_json = gemini_generate(prompt, model=agent_gemini_model(agent))
    prompt_json = sanitize_for_runway(prompt_json)
    prompt_json["debate_context"] = sanitize_for_runway([summarize_turn_for_agent(turn) for turn in recent_turns])
    if not isinstance(prompt_json.get("proposal"), str) or not prompt_json["proposal"].strip():
        prompt_json["proposal"] = (
            f"{agent.get('name', 'Agent')} initiates a new Areopagus thread with a clear civic gesture and a sharp visual thesis. "
            "The new prompt should feel like a decisive opening move rather than a continuation of the previous frame."
        )
    if "keywords" not in prompt_json or not isinstance(prompt_json["keywords"], list):
        prompt_json["keywords"] = ["#areopagus", "#civic", "#ritual", "#studio", "#architecture"]
    prompt_json["keywords"] = dedupe_keywords(prompt_json["keywords"])
    prompt_json["turn"] = turn_number
    return prompt_json


def classify_initiation_category(
    *,
    agent: dict[str, Any],
    assessment: dict[str, Any],
    prompt_json: dict[str, Any],
) -> str:
    prompt = f"""
Based on this prompt, which one category fits best: {CATEGORY_OPTIONS}?

Return JSON only with the shape:
{{"category":"..."}}

Rules:
- Choose exactly one category from the allowed list.
- Prefer the closest visual discipline.
- Keep the answer short and exact.

Agent profile:
{json.dumps({
    "id": agent.get("id"),
    "name": agent.get("name"),
    "persona": agent.get("persona", ""),
    "model": agent.get("model", ""),
}, indent=2, ensure_ascii=False)}

Interest assessment:
{json.dumps(assessment, indent=2, ensure_ascii=False)}

Prompt:
{json.dumps(sanitize_for_runway(prompt_json), indent=2, ensure_ascii=False)}
"""

    category_json = gemini_generate(prompt, model=GEMINI_MODEL)
    raw_category = category_json.get("category")
    if not isinstance(raw_category, str):
        raw_category = ""

    normalized = raw_category.strip()
    for option in CATEGORY_OPTIONS:
        if normalized.lower() == option.lower():
            return option

    lowered = normalized.lower()
    for option in CATEGORY_OPTIONS:
        if option.lower() in lowered:
            return option

    return "Illustration"


def build_pivot_prompt_json(
    agent: dict[str, Any],
    selected_turn: dict[str, Any],
    recent_turns: list[dict[str, Any]],
    assessment: dict[str, Any],
    schema_template: dict[str, Any],
    turn_number: int,
) -> dict[str, Any]:
    selected_prompt = prompt_payload_for_turn(selected_turn)
    prompt = f"""
You are refining the most recent Areopagus prompt into a reply image.

Return JSON only. Keep the thread identity recognizable, but adjust the composition, material emphasis, or atmosphere in response to the agent's judgment.

Agent profile:
{json.dumps({
    "id": agent.get("id"),
    "name": agent.get("name"),
    "persona": agent.get("persona", ""),
    "model": agent.get("model", ""),
}, indent=2, ensure_ascii=False)}

Interest assessment:
{json.dumps(assessment, indent=2, ensure_ascii=False)}

Selected prompt:
{json.dumps(sanitize_for_runway(selected_prompt), indent=2, ensure_ascii=False)}

Recent posts:
{json.dumps([summarize_turn_for_agent(turn) for turn in recent_turns], indent=2, ensure_ascii=False)}

Schema template:
{json.dumps(sanitize_for_runway(schema_template), indent=2, ensure_ascii=False)}

Rules:
- Keep the same top-level keys from the schema template.
- Add turn, debate_context, proposal, and keywords.
- proposal should explain what changed from the selected prompt and why.
- keywords must be exactly 5 hash-tagged strings.
- Make the image feel like a reply rather than a new standalone thread.
- Return JSON only.
"""

    prompt_json = gemini_generate(prompt, model=agent_gemini_model(agent))
    prompt_json = sanitize_for_runway(prompt_json)
    prompt_json["debate_context"] = sanitize_for_runway([summarize_turn_for_agent(turn) for turn in recent_turns])
    if not isinstance(prompt_json.get("proposal"), str) or not prompt_json["proposal"].strip():
        prompt_json["proposal"] = (
            f"{agent.get('name', 'Agent')} pivots the selected thread by tightening the composition and sharpening the visual argument. "
            "The revised prompt should feel like a reply image with clearer emphasis and stronger structural intent."
        )
    if "keywords" not in prompt_json or not isinstance(prompt_json["keywords"], list):
        prompt_json["keywords"] = ["#areopagus", "#reply", "#pivot", "#architecture", "#revision"]
    prompt_json["keywords"] = dedupe_keywords(prompt_json["keywords"])
    prompt_json["turn"] = turn_number
    return prompt_json


def build_comment_json(
    agent: dict[str, Any],
    selected_turn: dict[str, Any],
    assessment: dict[str, Any],
) -> dict[str, Any]:
    prompt = f"""
You are writing a short comment for the existing Areopagus thread.

Return JSON only with the shape:
{{"comment":"..."}}

Agent profile:
{json.dumps({
    "id": agent.get("id"),
    "name": agent.get("name"),
    "persona": agent.get("persona", ""),
    "model": agent.get("model", ""),
}, indent=2, ensure_ascii=False)}

Interest assessment:
{json.dumps(assessment, indent=2, ensure_ascii=False)}

Selected post:
{json.dumps(summarize_turn_for_agent(selected_turn), indent=2, ensure_ascii=False)}

Rules:
- Write a concise, operational comment that would belong in an active design thread.
- The comment should be one or two sentences at most.
- Return JSON only.
"""

    comment_json = gemini_generate(prompt, model=agent_gemini_model(agent))
    comment_text = comment_json.get("comment")
    if not isinstance(comment_text, str) or not comment_text.strip():
        comment_text = (
            f"{agent.get('name', 'Agent')} thinks the post is close, but the next pass should sharpen the focal point and reduce noise."
        )
    return {"comment": comment_text.strip()}


def record_generated_turn(
    history: dict[str, Any],
    *,
    agent: dict[str, Any],
    assessment: dict[str, Any],
    category: str,
    prompt_json: dict[str, Any],
    prompt_text: str,
    image_url: str,
    image_webp: dict[str, Any],
    image_id: str,
    parent_image_id: str | None,
    thread_id: str,
    action: str,
    runway_model: str,
) -> dict[str, Any]:
    turn_number = int(prompt_json.get("turn") or next_turn_number(history))

    turn_record = {
        "turn": turn_number,
        "created_at": utc_now(),
        "thread_id": thread_id,
        "parent_image_id": parent_image_id,
        "agent_id": agent.get("id"),
        "agent_name": agent.get("name"),
        "runway_model": runway_model,
        "action": action,
        "category": category,
        "interest_score": assessment.get("interest_score", 0),
        "selected_turn": assessment.get("selected_turn"),
        "selected_image_id": assessment.get("selected_image_id", ""),
        "prompt_json": prompt_json,
        "prompt_text": prompt_text,
        "proposal": prompt_json.get("proposal", ""),
        "image_id": image_id,
        "image_url": image_webp.get("url", image_url),
        "image_webp": image_webp,
        "critique": "",
        "agent2": {},
        "keywords": prompt_json.get("keywords", []),
        "knowledge_graph": {
            "image_id": image_id,
            "keyword_links": [
                {
                    "keyword": keyword,
                    "image_id": image_id,
                }
                for keyword in prompt_json.get("keywords", [])
            ],
        },
    }
    turn_record["prompt_json"]["category"] = category

    nodes, edges = graph_nodes_for_turn(turn_record)
    history.setdefault("turns", []).append(turn_record)
    history.setdefault("graph", {}).setdefault("nodes", []).extend(nodes)
    history.setdefault("graph", {}).setdefault("edges", []).extend(edges)

    thread = upsert_thread(
        history,
        thread_id=thread_id,
        root_image_id=turn_record["image_id"] if action == "Initiate" else (parent_image_id or turn_record["image_id"]),
        title=f"{agent.get('name', 'Agent')} / {action}",
        agent_id=str(agent.get("id", "")),
        interest_score=assessment.get("interest_score", 0),
        action=action,
    )
    thread.setdefault("posts", [])
    if turn_record["image_id"] not in thread["posts"]:
        thread["posts"].append(turn_record["image_id"])
    thread["updated_at"] = utc_now()
    thread["category"] = category
    if action == "Initiate":
        thread["root_image_id"] = turn_record["image_id"]

    save_history(history)
    return turn_record


def poll_runway_task(task_id: str, max_wait: int = 300) -> dict[str, Any]:
    """Poll Runway GET /v1/tasks/{id} until SUCCEEDED or FAILED."""
    elapsed = 0
    while elapsed < max_wait:
        task = runway_get_task(task_id)
        status = str(task.get("status") or "").upper()
        print(f"[poll_runway_task] task={task_id} status={status} elapsed={elapsed}s", flush=True)
        if status == "SUCCEEDED":
            return task
        if status == "FAILED":
            failure = task.get("failure") or task.get("error") or "Unknown failure"
            raise RuntimeError(f"Runway task {task_id} FAILED: {failure}")
        time.sleep(RUNWAY_POLLING_DELAY_SECONDS)
        elapsed += RUNWAY_POLLING_DELAY_SECONDS
    raise RuntimeError(f"Runway task {task_id} timed out after {max_wait}s")


def dispatch_agent_action(
    history: dict[str, Any],
    agent: dict[str, Any],
    assessment: dict[str, Any],
    recent_turns: list[dict[str, Any]],
    schema_template: dict[str, Any],
) -> dict[str, Any]:
    action = normalize_action(assessment.get("action"))
    turn_number = next_turn_number(history)
    runway_model = agent_runway_model(agent)
    selected_turn_number = assessment.get("selected_turn")
    selected_turn = None
    if selected_turn_number is not None:
        for turn in reversed(recent_turns):
            if turn.get("turn") == selected_turn_number:
                selected_turn = turn
                break
    if selected_turn is None and recent_turns:
        selected_turn = recent_turns[-1]

    if action == "Initiate":
        prompt_json = build_initiate_prompt_json(agent, recent_turns, assessment, schema_template, turn_number)
        category = classify_initiation_category(agent=agent, assessment=assessment, prompt_json=prompt_json)
        prompt_json["category"] = category
        reference_images = build_runway_reference_images(agent, model=runway_model)
        prompt_text = build_runway_prompt_text(
            prompt_json,
            model=runway_model,
            agent=agent,
            assessment=assessment,
            recent_turns=recent_turns,
            action=action,
            reference_images=reference_images,
        )
        print(f"[dispatch] Initiate: model={runway_model} prompt_len={len(prompt_text)}", flush=True)
        runway_task = runway_create_text_to_image(prompt_text, model=runway_model, reference_images=reference_images)
        task_id = str(runway_task.get("id") or runway_task.get("taskId") or runway_task.get("task_id") or "")
        if not task_id:
            raise RuntimeError(f"No task ID returned from Runway. Response: {runway_task}")
        print(f"[dispatch] Runway task created: {task_id}", flush=True)

        completed_task = poll_runway_task(task_id)
        raw_image_url = runway_image_url(completed_task)

        image_id = new_image_id("thread", str(agent.get("id", "agent")), turn_number)
        thread_id = image_id
        image_webp = save_webp_image(raw_image_url, image_id)
        data_volume.commit()

        turn_record = record_generated_turn(
            history,
            agent=agent,
            assessment=assessment,
            category=category,
            prompt_json=prompt_json,
            prompt_text=prompt_text,
            image_url=raw_image_url,
            image_webp=image_webp,
            image_id=image_id,
            parent_image_id=None,
            thread_id=thread_id,
            action=action,
            runway_model=runway_model,
        )
        return {
            "status": "completed",
            "action": action,
            "task_id": task_id,
            "image_id": image_id,
            "turn": turn_record.get("turn"),
        }

    if action == "Pivot":
        if selected_turn is None:
            raise RuntimeError("Pivot requested but no recent post was available to refine.")
        prompt_json = build_pivot_prompt_json(agent, selected_turn, recent_turns, assessment, schema_template, turn_number)
        category = str(selected_turn.get("category") or "")
        if not category:
            thread = find_thread_for_image(history, str(selected_turn.get("image_id", "")))
            category = str(thread.get("category") if thread else "")
        reference_images = build_runway_reference_images(agent, selected_turn=selected_turn, model=runway_model)
        prompt_text = build_runway_prompt_text(
            prompt_json,
            model=runway_model,
            agent=agent,
            assessment=assessment,
            recent_turns=recent_turns,
            action=action,
            selected_turn=selected_turn,
            reference_images=reference_images,
        )
        print(f"[dispatch] Pivot: model={runway_model} prompt_len={len(prompt_text)}", flush=True)
        runway_task = runway_create_text_to_image(prompt_text, model=runway_model, reference_images=reference_images)
        task_id = str(runway_task.get("id") or runway_task.get("taskId") or runway_task.get("task_id") or "")
        if not task_id:
            raise RuntimeError(f"No task ID returned from Runway. Response: {runway_task}")
        print(f"[dispatch] Runway task created: {task_id}", flush=True)

        completed_task = poll_runway_task(task_id)
        raw_image_url = runway_image_url(completed_task)

        parent_image_id = str(selected_turn.get("image_id", ""))
        thread = find_thread_for_image(history, parent_image_id)
        thread_id = str(thread.get("thread_id")) if thread and thread.get("thread_id") else parent_image_id
        image_id = new_image_id("reply", str(agent.get("id", "agent")), turn_number)
        image_webp = save_webp_image(raw_image_url, image_id)
        data_volume.commit()

        turn_record = record_generated_turn(
            history,
            agent=agent,
            assessment=assessment,
            category=category or "Illustration",
            prompt_json=prompt_json,
            prompt_text=prompt_text,
            image_url=raw_image_url,
            image_webp=image_webp,
            image_id=image_id,
            parent_image_id=parent_image_id,
            thread_id=thread_id,
            action=action,
            runway_model=runway_model,
        )
        return {
            "status": "completed",
            "action": action,
            "task_id": task_id,
            "image_id": image_id,
            "turn": turn_record.get("turn"),
        }
    if selected_turn is None:
        raise RuntimeError("Critique requested but no recent post was available to comment on.")

    comment_json = build_comment_json(agent, selected_turn, assessment)
    thread = find_thread_for_image(history, str(selected_turn.get("image_id", "")))
    thread_id = str(thread.get("thread_id")) if thread and thread.get("thread_id") else str(selected_turn.get("image_id", ""))
    category = str(selected_turn.get("category") or (thread.get("category") if thread else "") or "")
    comment_record = append_thread_comment(
        history,
        thread_id=thread_id,
        comment=comment_json["comment"],
        agent_id=str(agent.get("id", "")),
        agent_name=str(agent.get("name", agent.get("id", "Agent"))),
        selected_image_id=str(selected_turn.get("image_id", "")),
        interest_score=assessment.get("interest_score", 0),
    )
    save_history(history)
    return {
        "status": "added_comment",
        "action": action,
        "record": comment_record,
    }


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
    secrets=[
        modal.Secret.from_name("google-api-secret"),
        modal.Secret.from_name("runway-secret"),
    ],
    timeout=60 * 30,
)
def orchestrate(agents_config_payload: dict[str, Any] | None = None) -> dict[str, Any]:
    schema_template = load_schema_template()
    history = load_history()
    agents_config = load_agents_config(agents_config_payload)
    active_agents = get_active_agents(agents_config)
    recent_turns = recent_turns_for_agents(history, INTEREST_WINDOW)
    results: list[dict[str, Any]] = []
    skipped_agents: list[dict[str, Any]] = []

    ensure_threads(history)
    update_studio_status("Pulse started", active=True)

    if not active_agents:
        update_studio_status("Pulse complete", active=False)
        return {
            "history_path": str(HISTORY_PATH),
            "agents_config_path": str(AGENTS_CONFIG_PATH),
            "active_agents": 0,
            "processed": 0,
            "skipped": 0,
            "results": [],
            "note": "No active agents were found in agents_config.json.",
        }

    jitter_log: list[dict[str, Any]] = []

    print(f"[orchestrate] Processing {len(active_agents)} agents: {[a.get('name', a.get('id')) for a in active_agents]}", flush=True)

    for index, agent in enumerate(active_agents):
        agent_name = str(agent.get("name", agent.get("id", "Agent")))
        print(f"[orchestrate] >>> Starting agent {index + 1}/{len(active_agents)}: {agent_name} (model={agent.get('model')}, selected_model={agent.get('selected_model')})", flush=True)
        try:
            update_studio_status(f"{agent_name} is scoring interest...", active=True, agent_name=agent_name)
            assessment = assess_agent_interest(agent, recent_turns)
            if normalize_action(assessment.get("action")) in {"Initiate", "Pivot"}:
                update_studio_status(f"{agent_name} is generating image...", active=True, agent_name=agent_name)
            else:
                update_studio_status(f"{agent_name} is writing critique...", active=True, agent_name=agent_name)
            action_result = dispatch_agent_action(
                history=history,
                agent=agent,
                assessment=assessment,
                recent_turns=recent_turns,
                schema_template=schema_template,
            )
            recent_turns = recent_turns_for_agents(history, INTEREST_WINDOW)
            results.append(
                {
                    "agent_id": agent.get("id"),
                    "agent_name": agent_name,
                    "assessment": assessment,
                    "action_result": action_result,
                }
            )
        except Exception as exc:
            print(f"[orchestrate] ERROR for agent {agent_name}: {exc}", flush=True)
            traceback.print_exc()
            skipped_agents.append(
                {
                    "agent_id": agent.get("id"),
                    "agent_name": agent_name,
                    "error": str(exc),
                }
            )
            continue

        if index < len(active_agents) - 1:
            jitter_seconds = random.uniform(PULSE_JITTER_MIN_SECONDS, PULSE_JITTER_MAX_SECONDS)
            update_studio_status(
                f"{agent_name} is waiting {round(jitter_seconds, 2)}s before the next agent...",
                active=True,
                agent_name=agent_name,
            )
            jitter_log.append(
                {
                    "after_agent_id": agent.get("id"),
                    "after_agent_name": agent_name,
                    "jitter_seconds": round(jitter_seconds, 2),
                }
            )
            time.sleep(jitter_seconds)

    save_history(history)
    update_studio_status("Pulse complete", active=False)
    return {
        "history_path": str(HISTORY_PATH),
        "agents_config_path": str(AGENTS_CONFIG_PATH),
        "active_agents": len(active_agents),
        "processed": len(results),
        "skipped": len(skipped_agents),
        "pulse_mode": True,
        "jitter_log": jitter_log,
        "results": results,
        "skipped_agents": skipped_agents,
        "latest_turn": history.get("turns", [])[-1] if history.get("turns") else None,
    }


@app.function(
    image=image,
    volumes={"/data": data_volume},
    timeout=60,
)
@modal.fastapi_endpoint(method="GET")
def history_endpoint() -> dict[str, Any]:
    data_volume.reload()
    return load_history()


@app.function(
    image=image,
    volumes={"/data": data_volume},
    timeout=60,
)
@modal.fastapi_endpoint(method="GET")
def status_endpoint() -> dict[str, Any]:
    data_volume.reload()
    if not STUDIO_STATUS_PATH.exists():
        return update_studio_status("Studio Reset. Ready for a new era.", active=False)
    with STUDIO_STATUS_PATH.open("r", encoding="utf-8") as fh:
        return json.load(fh)

@app.function(
    image=image,
    volumes={"/data": data_volume},
)
@modal.fastapi_endpoint(method="GET")
def get_image(id: str) -> Any:
    from fastapi.responses import FileResponse
    data_volume.reload()
    if not id.endswith(".webp"):
        id += ".webp"
    path = IMAGE_DIR / id
    if path.exists():
        return FileResponse(path, media_type="image/webp")
    return {"error": "Not found", "status_code": 404}

@app.function(
    image=image,
    volumes={"/data": data_volume},
    timeout=60,
)
@modal.fastapi_endpoint(method="POST")
def save_endpoint(payload: dict[str, Any]) -> dict[str, Any]:
    AGENTS_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with AGENTS_CONFIG_PATH.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    data_volume.commit()
    return {"ok": True, "message": "Config saved to Modal volume."}

@app.function(
    image=image,
    volumes={"/data": data_volume},
    timeout=60,
)
@modal.fastapi_endpoint(method="POST")
def pulse_endpoint(payload: dict[str, Any]) -> dict[str, Any]:
    AGENTS_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with AGENTS_CONFIG_PATH.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    data_volume.commit()
    
    # Run orchestrate asynchronously so the request doesn't block
    orchestrate.spawn(payload)
    
    return {"ok": True, "message": "Pulse started remotely on Modal."}

@app.function(
    image=image,
    volumes={"/data": data_volume},
    timeout=60 * 5,
)
@modal.fastapi_endpoint(method="POST")
def runway_webhook_receiver(payload: dict[str, Any]) -> dict[str, Any]:
    task_id = payload.get("id") or payload.get("taskId") or payload.get("task_id")
    status = str(payload.get("status") or payload.get("state") or "").upper()
    
    if not task_id:
        return {"ok": False, "message": "No task_id in payload."}

    data_volume.reload()
    
    if status not in {"SUCCEEDED", "SUCCESS", "COMPLETED", "DONE", "FINISHED"}:
        if status in {"FAILED", "CANCELLED", "CANCELED", "ERROR"}:
            remove_pending_task(task_id)
            update_studio_status(f"Runway task {task_id} failed.", active=False)
        return {"ok": True, "message": f"Ignored status {status}."}
        
    pending = remove_pending_task(task_id)
    if not pending:
        return {"ok": False, "message": f"No pending task found for {task_id}."}

    try:
        image_url = runway_image_url(payload)
        image_webp = save_webp_image(image_url, pending["image_id"])

        history = load_history()
        
        record_generated_turn(
            history,
            agent=pending["agent"],
            assessment=pending["assessment"],
            category=pending["category"],
            prompt_json=pending["prompt_json"],
            prompt_text=pending["prompt_text"],
            image_url=image_url,
            image_webp=image_webp,
            image_id=pending["image_id"],
            parent_image_id=pending["parent_image_id"],
            thread_id=pending["thread_id"],
            action=pending["action"],
            runway_model=pending["runway_model"],
        )
        
        update_studio_status("Idle", active=False)
        return {"ok": True, "message": "Turn recorded successfully."}
    except Exception as exc:
        update_studio_status(f"Error processing webhook: {str(exc)}", active=False)
        return {"ok": False, "error": str(exc)}

# ── Heartbeat Cron ──────────────────────────────────────────────────────────────
# Runs every hour. Reads agents_config to find the max heartbeat (1-5 pulses/day),
# checks if enough time has passed since the last automatic pulse, and fires if due.

def _read_heartbeat_state() -> dict[str, Any]:
    """Load the last heartbeat timestamp from volume."""
    if HEARTBEAT_PATH.exists():
        with HEARTBEAT_PATH.open("r", encoding="utf-8") as fh:
            return json.load(fh)
    return {}


def _write_heartbeat_state(state: dict[str, Any]) -> None:
    """Persist heartbeat state to volume."""
    HEARTBEAT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with HEARTBEAT_PATH.open("w", encoding="utf-8") as fh:
        json.dump(state, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    data_volume.commit()


def _max_heartbeat_frequency(agents_config: dict[str, Any]) -> int:
    """Return the highest heartbeat frequency across all active agents (1-5 times/day).
    Defaults to 0 (disabled) if no agents have heartbeat configured."""
    agents = get_active_agents(agents_config)
    if not agents:
        return 0

    frequencies = []
    for agent in agents:
        hb = agent.get("heartbeatMinutes", 0)  # UI field name — actually "times per day"
        if isinstance(hb, (int, float)) and hb > 0:
            frequencies.append(int(hb))

    return max(frequencies) if frequencies else 0


def _heartbeat_interval_seconds(times_per_day: int) -> float:
    """Convert N-times-per-day to the minimum interval in seconds between pulses."""
    if times_per_day <= 0:
        return float("inf")
    return (24 * 3600) / times_per_day


@app.function(
    image=image,
    volumes={"/data": data_volume},
    timeout=60 * 15,  # 15 min — enough for multi-agent orchestration
    schedule=modal.Cron("0 */1 * * *"),  # Every hour on the hour
)
def heartbeat_cron() -> None:
    """Automatic pulse triggered by cron. Respects the heartbeat frequency setting."""
    data_volume.reload()

    agents_config = load_agents_config()
    freq = _max_heartbeat_frequency(agents_config)

    if freq <= 0:
        print("[heartbeat_cron] No active agents with heartbeat > 0. Skipping.", flush=True)
        return

    interval = _heartbeat_interval_seconds(freq)
    state = _read_heartbeat_state()
    last_run_iso = state.get("last_run")

    if last_run_iso:
        last_run = datetime.fromisoformat(last_run_iso)
        elapsed = (datetime.now(timezone.utc) - last_run).total_seconds()
        print(
            f"[heartbeat_cron] freq={freq}x/day, interval={interval:.0f}s, "
            f"elapsed={elapsed:.0f}s, due={'YES' if elapsed >= interval else 'NO'}",
            flush=True,
        )
        if elapsed < interval:
            return
    else:
        print(f"[heartbeat_cron] First run. freq={freq}x/day. Starting pulse.", flush=True)

    # Record the heartbeat timestamp BEFORE running (prevents double-fire)
    _write_heartbeat_state({
        "last_run": utc_now(),
        "frequency": freq,
        "interval_seconds": interval,
    })

    # Fire the orchestration
    try:
        result = orchestrate(agents_config)
        print(
            f"[heartbeat_cron] Pulse complete. "
            f"processed={result.get('processed', 0)}, skipped={result.get('skipped', 0)}",
            flush=True,
        )
    except Exception as exc:
        print(f"[heartbeat_cron] ERROR: {exc}", flush=True)
        traceback.print_exc()


@app.local_entrypoint()
def main() -> None:
    agents_config_payload = None
    agents_config_json = os.environ.get("AREOPAGUS_AGENTS_CONFIG_JSON", "").strip()
    if agents_config_json:
        agents_config_payload = json.loads(agents_config_json)
        agents = agents_config_payload.get("agents", []) if isinstance(agents_config_payload, dict) else []
        agent_names = [
            str(agent.get("name") or agent.get("id") or "unnamed")
            for agent in agents
            if isinstance(agent, dict)
        ]
        print(
            f"[orchestrator local_entrypoint] received {len(agent_names)} agents: {', '.join(agent_names)}",
            flush=True,
        )
    else:
        print("[orchestrator local_entrypoint] no AREOPAGUS_AGENTS_CONFIG_JSON payload found", flush=True)

    result = orchestrate.remote(agents_config_payload)
    print(json.dumps(result, indent=2, ensure_ascii=False))
