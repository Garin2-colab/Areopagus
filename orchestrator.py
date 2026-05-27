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
import urllib.parse
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
        "16:9": "1920:1088",
        "9:16": "1088:1920",
        "4:3": "1920:1440",
        "3:4": "1440:1920",
        "21:9": "2048:880",
        "2:3": "1280:1920",
        "3:2": "1920:1280",
        "4:5": "1536:1920",
        "5:4": "1920:1536",
    },
    "gemini_image3_pro": {
        "1:1": "1024:1024",
        "16:9": "1344:768",
        "9:16": "768:1344",
        "4:3": "1184:864",
        "3:4": "864:1184",
        "21:9": "1536:672",
        "2:3": "832:1248",
        "3:2": "1248:832",
        "4:5": "896:1152",
        "5:4": "1152:896",
    },
    "gen4_image": {
        "1:1": "1080:1080",
    },
    "gen4_image_turbo": {
        "1:1": "1080:1080",
    },
    "gemini_2.5_flash": {
        "1:1": "1024:1024",
        "16:9": "1344:768",
        "9:16": "768:1344",
        "4:3": "1184:864",
        "3:4": "864:1184",
        "21:9": "1536:672",
        "2:3": "832:1248",
        "3:2": "1248:832",
        "4:5": "896:1152",
        "5:4": "1152:896",
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
    .add_local_dir("./models", remote_path="/root/models")
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

    # Check if we should upgrade the graph nodes to the connected-mesh schema
    has_connected_mesh = False
    for node in history["graph"].get("nodes", []):
        if isinstance(node, dict) and str(node.get("id", "")).startswith("keyword-"):
            has_connected_mesh = True
            break
    if not has_connected_mesh and len(history.get("turns", [])) > 0:
        print("[load_history] Upgrading graph nodes to connected-mesh schema...", flush=True)
        rebuild_history_graph(history)
        with HISTORY_PATH.open("w", encoding="utf-8") as fh:
            json.dump(history, fh, indent=2, ensure_ascii=False)
            fh.write("\n")
        data_volume.commit()

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



def update_studio_status(message: str, active: bool = True, agent_name: str | None = None, active_nodes: list[str] | None = None) -> dict[str, Any]:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    
    # Load existing status and history log list
    history = []
    if STUDIO_STATUS_PATH.exists():
        try:
            with STUDIO_STATUS_PATH.open("r", encoding="utf-8") as fh:
                old_status = json.load(fh)
                history = old_status.get("history", [])
        except Exception:
            pass

    # If new pulse is starting, reset log history
    if message == "Pulse started":
        history = []

    # Format the new log entry
    entry = {
        "message": message,
        "active": active,
        "timestamp": utc_now(),
    }
    if agent_name:
        entry["agent_name"] = agent_name

    # Only append if history is empty or if this message is new
    if not history or history[-1].get("message") != message:
        history.append(entry)

    # Limit history to the last 100 logs to keep status.json reasonably sized
    if len(history) > 100:
        history = history[-100:]

    status = {
        "message": message,
        "active": active,
        "updated_at": utc_now(),
        "history": history,
    }
    if agent_name:
        status["agent_name"] = agent_name
    if active_nodes is not None:
        status["active_nodes"] = active_nodes

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


def userapi_api_key() -> str:
    return os.environ.get("USERAPI_API_KEY", "").strip()


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


# Runway, Midjourney, and Seedance helper functions have been modularized and moved to the models/ package.



def save_mp4_video(video_url: str, image_id: str, aspect_ratio: str = "16:9") -> dict[str, Any]:
    video_bytes, source_mime_type = fetch_image_bytes(video_url)
    IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    mp4_path = IMAGE_DIR / f"{image_id}.mp4"

    with open(mp4_path, "wb") as f:
        f.write(video_bytes)

    ratios = {
        "1:1": (480, 480),
        "4:3": (640, 480),
        "3:4": (360, 480),
        "16:9": (854, 480),
        "9:16": (270, 480),
        "21:9": (1120, 480),
    }
    width, height = ratios.get(aspect_ratio, (854, 480))

    try:
        web_url = get_image.get_web_url()
    except Exception:
        web_url = None

    if not web_url:
        web_url = "https://heebok-lee--areopagus-get-image.modal.run"

    web_url = web_url.rstrip("/")

    return {
        "path": str(mp4_path),
        "url": f"{web_url}/?id={image_id}",
        "format": "mp4",
        "source_mime_type": source_mime_type or "video/mp4",
        "size_bytes": mp4_path.stat().st_size,
        "dimensions": {
            "width": width,
            "height": height,
        },
    }


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
  scene_description, aspect_ratio.
- `scene_description` must be one long paragraph (2 to 5 descriptive sentences) containing the entire visual prompt details (blending subject, attire, lighting, environment, color palette, style, and camera).
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


def fetch_image_bytes(image_url: str) -> tuple[bytes, str]:
    if "id=" in image_url:
        try:
            parsed = urllib.parse.urlparse(image_url)
            query = urllib.parse.parse_qs(parsed.query)
            image_id = query.get("id", [None])[0]
            if image_id:
                if image_id.endswith(".webp") or image_id.endswith(".mp4"):
                    image_id = image_id.rsplit(".", 1)[0]
                mp4_path = IMAGE_DIR / f"{image_id}.mp4"
                if mp4_path.exists():
                    return mp4_path.read_bytes(), "video/mp4"
                local_path = IMAGE_DIR / f"{image_id}.webp"
                if local_path.exists():
                    return local_path.read_bytes(), "image/webp"
        except Exception as err:
            print(f"[fetch_image_bytes] local path check failed: {err}", flush=True)

    try:
        req = urllib.request.Request(
            image_url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            }
        )
        with urllib.request.urlopen(req) as response:
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
        # Preserve original aspect ratio but scale down so the maximum dimension is 1080
        w, h = source.size
        if w > h:
            target_w = 1080
            target_h = int(1080 * (h / w))
        else:
            target_h = 1080
            target_w = int(1080 * (w / h))
        converted = source.convert("RGB").resize((target_w, target_h), Image.Resampling.LANCZOS)
        converted.save(webp_path, "WEBP", quality=WEBP_QUALITY, method=6)
        width, height = converted.size

    # Try to resolve get_image URL dynamically to make the app portable
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


# agent_runway_model has been replaced by the models.get_model registry pattern



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


# runway_ratio_for_model and runway_reference_limit are modularized inside runway.py



def agent_style_slots(agent: dict[str, Any]) -> list[str]:
    agent_refs = agent.get("referenceImages") or agent.get("reference_images") or []
    if isinstance(agent_refs, dict):
        agent_refs = [agent_refs]
    slots = []
    if isinstance(agent_refs, list):
        for idx, ref in enumerate(agent_refs):
            has_val = False
            if isinstance(ref, str) and ref.strip():
                has_val = True
            elif isinstance(ref, dict) and (ref.get("uri") or ref.get("url") or ref.get("image_url")):
                has_val = True
            if has_val:
                slots.append(f"AgentRef{idx+1}")
    return slots


# build_runway_reference_images and associated helpers are modularized inside models package



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
- Give an `initiate_score` from 0 to 100 based on the agent's persona and current creative energy.
- For each of the recent posts, give an `interest_score` from 0 to 100. If a post is highly relevant, score it high. If it is mundane or irrelevant to their aesthetics, score it low.
- To act like a human, be highly selective: agents do not react to everything. An interest score below 50 means they will ignore it.
- For each post, decide the best reply `action` if the agent were to reply:
  - Use `Pivot` when the agent wants to reply by generating a new image inspired by the post.
  - Use `Critique` when the agent wants to reply with text only (commenting).
- Keep reasons short, character-driven, and active.
"""

    assessment = gemini_generate(prompt, model=agent_gemini_model(agent))
    assessment["agent_id"] = agent.get("id")
    assessment["agent_name"] = agent.get("name", agent.get("id", "Agent"))
    
    # Introduce human-like behavioral mood jittering (-12 to +12)
    raw_initiate = clamp_interest_score(assessment.get("initiate_score"))
    initiate_score = clamp_interest_score(raw_initiate + random.uniform(-12, 12))

    post_scores = assessment.get("post_scores", [])
    if not isinstance(post_scores, list):
        post_scores = []

    normalized_scores: list[dict[str, Any]] = []
    for score in post_scores:
        if not isinstance(score, dict):
            continue
        raw_score = clamp_interest_score(score.get("interest_score"))
        jittered_score = clamp_interest_score(raw_score + random.uniform(-12, 12))
        normalized_scores.append(
            {
                "turn": score.get("turn"),
                "image_id": score.get("image_id"),
                "interest_score": jittered_score,
                "action": normalize_action(score.get("action")),
                "reason": score.get("reason", ""),
            }
        )

    # 15% probability of a pure whim/impulse override
    is_whim = random.random() < 0.15
    best_post_score = max(normalized_scores, key=lambda item: item["interest_score"]) if normalized_scores else None

    if is_whim and normalized_scores:
        # Flip a coin: either initiate a new thread, or reply to a random post
        whim_choice = random.choice(["initiate", "reply"])
        if whim_choice == "initiate":
            assessment["selected_turn"] = None
            assessment["selected_image_id"] = ""
            assessment["interest_score"] = initiate_score
            assessment["action"] = "Initiate"
            assessment["reason"] = f"[Whim] A sudden spark of inspiration led {agent.get('name')} to start a new thread."
            print(f"[orchestrate] WHIM: {agent.get('name')} chose to INITIATE a new thread on a whim.", flush=True)
        else:
            random_post = random.choice(normalized_scores)
            assessment["selected_turn"] = random_post.get("turn")
            assessment["selected_image_id"] = random_post.get("image_id")
            assessment["interest_score"] = random_post["interest_score"]
            assessment["action"] = random_post["action"]
            assessment["reason"] = f"[Whim] A passing detail caught {agent.get('name')}'s eye, compelling them to react: {random_post.get('reason')}"
            print(f"[orchestrate] WHIM: {agent.get('name')} chose to interact with Turn {random_post.get('turn')} on a whim.", flush=True)
    else:
        # Standard logical selection based on highest jittered score
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
            assessment["reason"] = assessment.get("initiate_reason", f"{agent.get('name')} prefers to initiate a new thread.")

    assessment["post_scores"] = normalized_scores
    return assessment


def retrieve_associative_memory(
    history: dict[str, Any],
    current_keywords: list[str],
    exclude_thread_id: str | None = None
) -> dict[str, Any] | None:
    """
    Traverse the graph in history.json using current_keywords to find a historical turn
    or user-uploaded inspiration image that shares keywords.
    """
    if not history:
        return None

    candidates = []
    current_keywords_set = {k.lower() for k in current_keywords}

    # Search normal turns
    for turn in history.get("turns", []):
        if not isinstance(turn, dict) or "image_id" not in turn:
            continue

        if exclude_thread_id and turn.get("thread_id") == exclude_thread_id:
            continue

        turn_keywords = {k.lower() for k in turn.get("keywords", [])}
        overlap = turn_keywords.intersection(current_keywords_set)
        if overlap:
            # We score it based on overlap length and turn number
            candidates.append((len(overlap), turn.get("turn", 0), turn))

    # Search user-uploaded inspiration images
    for insp in history.get("inspiration", []):
        if not isinstance(insp, dict) or "id" not in insp:
            continue

        insp_keywords = {k.lower() for k in insp.get("keywords", [])}
        overlap = insp_keywords.intersection(current_keywords_set)
        if overlap:
            # Map id to image_id, and turn to simulated values so caller parses cleanly
            insp_copy = dict(insp)
            insp_copy["image_id"] = insp["id"]
            insp_copy["turn"] = "Inspiration"
            insp_copy["proposal"] = "User Uploaded Inspiration"
            # Assign simulated high relevance (e.g. 9999) to prioritize user-uploaded references
            candidates.append((len(overlap), 9999, insp_copy))

    if not candidates:
        return None

    # Sort candidates by overlap descending, then by turn/relevance descending
    candidates.sort(key=lambda x: (x[0], x[1]), reverse=True)
    return candidates[0][2]


def build_initiate_prompt_json(
    agent: dict[str, Any],
    recent_turns: list[dict[str, Any]],
    assessment: dict[str, Any],
    schema_template: dict[str, Any],
    turn_number: int,
    history: dict[str, Any] | None = None,
) -> dict[str, Any]:
    # Download baseline agent reference image bytes if configured
    image_bytes = None
    image_mime_type = None
    prompt_img_url = agent.get("prompt_image") or agent.get("promptImage")
    if prompt_img_url:
        try:
            image_bytes, image_mime_type = fetch_image_bytes(prompt_img_url)
        except Exception as e:
            print(f"[warning] Failed to fetch agent prompt image: {e}", flush=True)

    # Walk graph to fetch inspiration memory
    extra_images = []
    inspiration_image_id = None
    inspiration_meta = None
    if history and recent_turns:
        recent_keywords = []
        recent_thread_ids = set()
        for turn in recent_turns:
            recent_keywords.extend(turn.get("keywords", []))
            if turn.get("thread_id"):
                recent_thread_ids.add(turn["thread_id"])
        
        if recent_keywords:
            memory = retrieve_associative_memory(history, recent_keywords)
            # Ensure it is not from the immediate active thread contexts
            if memory and memory.get("thread_id") not in recent_thread_ids:
                inspiration_url = memory.get("image_url")
                if inspiration_url:
                    try:
                        mem_bytes, mem_mime = fetch_image_bytes(inspiration_url)
                        extra_images.append((mem_bytes, mem_mime))
                        inspiration_image_id = memory.get("image_id")
                        inspiration_meta = memory
                        print(f"[inspiration] Initiator recalled Turn {memory.get('turn')} ({inspiration_image_id}) via keywords {memory.get('keywords')}", flush=True)
                    except Exception as e:
                        print(f"[warning] Failed to fetch inspiration image for initiation: {e}", flush=True)

    style_slots = agent_style_slots(agent)
    agent_profile = {
        "id": agent.get("id"),
        "name": agent.get("name"),
        "persona": agent.get("persona", ""),
        "model": agent.get("model", ""),
    }
    if style_slots:
        agent_profile["style_slots"] = style_slots

    prompt = f"""
You are drafting a brand-new Areopagus thread.
"""
    if prompt_img_url:
        prompt += "\nYou are shown your baseline style reference image (AgentPrompt) in the multimodal context. You can reference it in your prompt fields using the tag '@ReferenceImage' to maintain persona style consistency."

    if inspiration_image_id and inspiration_meta:
        prompt += f"""
NOTE: An associative memory from the Knowledge Web has been recalled:
- Inspiration Turn: Turn {inspiration_meta.get('turn')}
- Inspiration Image ID: {inspiration_image_id}
- Inspiration Keywords: {inspiration_meta.get('keywords')}
- Inspiration Proposal: "{inspiration_meta.get('proposal')}"

This image is attached to your visual context with the tag '@InspirationRef'. If you choose to blend its concepts, styles, or compositions, you must reference '@InspirationRef' in your style or description fields, and you must set `"inspiration_image_id": "{inspiration_image_id}"` in the returned JSON. If you do not choose to reference it, set `"inspiration_image_id": null`.
"""

    prompt += f"""

Return JSON only. Use the schema template below as the structural guide, then expand it into a fresh prompt that feels like a new thread rather than a revision.

Agent profile:
{json.dumps(agent_profile, indent=2, ensure_ascii=False)}

Interest assessment:
{json.dumps(assessment, indent=2, ensure_ascii=False)}

Recent posts:
{json.dumps([summarize_turn_for_agent(turn) for turn in recent_turns], indent=2, ensure_ascii=False)}

Schema template:
{json.dumps(sanitize_for_runway(schema_template), indent=2, ensure_ascii=False)}

Rules:
- Keep the same top-level keys from the schema template: scene_description, aspect_ratio.
- `scene_description` must be one long paragraph (2 to 5 descriptive sentences) containing the entire visual prompt details (blending subject, attire, lighting, environment, color palette, style, and camera).
- Add turn, debate_context, proposal, keywords, reference_image_id, and inspiration_image_id.
- proposal should be 2 to 3 sentences and should explain the design move the agent is initiating.
- keywords must be exactly 5 simple, intuitive, hash-tagged strings. Avoid complex, composite/merged words like '#impossiblegeometryflux' or '#monochromeminimalism'. Instead, split them into separate simple concepts (e.g. '#impossiblegeometry', '#flux'; '#monochrome', '#minimalism'). NEVER use generic words like '#inspiration', '#design', '#image', '#photo', '#art', or '#aesthetic'.
- For `aspect_ratio`, dynamically select the most appropriate aspect ratio for the visual composition you are designing. Choose strictly from the following allowed ratios: ["1:1", "16:9", "9:16", "4:3", "3:4", "21:9", "2:3", "3:2", "4:5", "5:4"]. For example, use "16:9" or "21:9" for expansive horizontal landscapes, "9:16" or "3:4" for vertical/portrait/human figures, and "1:1" for focused central/abstract compositions.
- reference_image_id: You must decide whether to use a style/composition reference image for this generation or generate completely from scratch.
  - If you want to use your baseline style image as a reference, set reference_image_id to "profile".
  - If you want to use one of your general reference style images from the profile, set reference_image_id to the slot name (e.g. "AgentRef1", "AgentRef2", etc.) if present in your style_slots.
  - If you want to generate completely from scratch without image references, set reference_image_id to null.
- If reference_image_id is NOT null, you must reference '@ReferenceImage' inside `scene_description`. If it is null, do NOT use the '@ReferenceImage' tag.
- If you want to reference another style slot (e.g. @AgentRef2) without making it the primary visual guide, you can use its tag anywhere in prompt text.
- inspiration_image_id: Set this to the string ID of the inspiration image (e.g., "{inspiration_image_id or ''}") if you referenced it, or null.
- The output should feel cinematic, architectural, ceremonial, and specific to the active agent persona.
"""
    if prompt_img_url:
        prompt += "- If appropriate, reference '@ReferenceImage' in your prompt fields to anchor the style."

    prompt += "\n- Return JSON only.\n"

    prompt_json = gemini_generate(
        prompt,
        image_bytes=image_bytes,
        image_mime_type=image_mime_type,
        extra_images=extra_images if extra_images else None,
        model=agent_gemini_model(agent)
    )
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
    if "inspiration_image_id" not in prompt_json:
        prompt_json["inspiration_image_id"] = inspiration_image_id
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
    history: dict[str, Any] | None = None,
) -> dict[str, Any]:
    selected_prompt = prompt_payload_for_turn(selected_turn)
    
    # Download the parent image bytes to feed into Gemini for visual analysis
    image_bytes = None
    image_mime_type = None
    if selected_turn and selected_turn.get("image_url"):
        try:
            image_bytes, image_mime_type = fetch_image_bytes(selected_turn["image_url"])
        except Exception as e:
            print(f"[warning] Failed to fetch image bytes for selected turn pivot: {e}", flush=True)

    # Walk graph to fetch inspiration memory based on selected_turn's keywords
    extra_images = []
    inspiration_image_id = None
    inspiration_meta = None
    if history and selected_turn:
        selected_keywords = selected_turn.get("keywords", [])
        exclude_thread_id = selected_turn.get("thread_id")
        if selected_keywords:
            memory = retrieve_associative_memory(history, selected_keywords, exclude_thread_id=exclude_thread_id)
            if memory:
                inspiration_url = memory.get("image_url")
                if inspiration_url:
                    try:
                        mem_bytes, mem_mime = fetch_image_bytes(inspiration_url)
                        extra_images.append((mem_bytes, mem_mime))
                        inspiration_image_id = memory.get("image_id")
                        inspiration_meta = memory
                        print(f"[inspiration] Pivot recalled Turn {memory.get('turn')} ({inspiration_image_id}) via keywords {memory.get('keywords')}", flush=True)
                    except Exception as e:
                        print(f"[warning] Failed to fetch inspiration image for pivot: {e}", flush=True)

    style_slots = agent_style_slots(agent)
    agent_profile = {
        "id": agent.get("id"),
        "name": agent.get("name"),
        "persona": agent.get("persona", ""),
        "model": agent.get("model", ""),
    }
    if style_slots:
        agent_profile["style_slots"] = style_slots

    prompt = f"""
You are refining the most recent Areopagus prompt into a reply image.
You are shown the actual generated image of the parent post (selected turn) in the multimodal context.
"""

    if inspiration_image_id and inspiration_meta:
        prompt += f"""
NOTE: An associative memory from the Knowledge Web has been recalled:
- Inspiration Turn: Turn {inspiration_meta.get('turn')}
- Inspiration Image ID: {inspiration_image_id}
- Inspiration Keywords: {inspiration_meta.get('keywords')}
- Inspiration Proposal: "{inspiration_meta.get('proposal')}"

This image is attached to your visual context with the tag '@InspirationRef'. If you choose to blend its concepts, styles, or compositions, you must reference '@InspirationRef' in your style or description fields, and you must set `"inspiration_image_id": "{inspiration_image_id}"` in the returned JSON. If you do not choose to reference it, set `"inspiration_image_id": null`.
"""

    prompt += f"""

Agent profile:
{json.dumps(agent_profile, indent=2, ensure_ascii=False)}

Interest assessment:
{json.dumps(assessment, indent=2, ensure_ascii=False)}

Selected prompt:
{json.dumps(sanitize_for_runway(selected_prompt), indent=2, ensure_ascii=False)}

Recent posts:
{json.dumps([summarize_turn_for_agent(turn) for turn in recent_turns], indent=2, ensure_ascii=False)}

Schema template:
{json.dumps(sanitize_for_runway(schema_template), indent=2, ensure_ascii=False)}

Rules:
Rules:
- Keep the same top-level keys from the schema template: scene_description, aspect_ratio.
- `scene_description` must be one long paragraph (2 to 5 descriptive sentences) containing the entire visual prompt details (blending subject, attire, lighting, environment, color palette, style, and camera).
- Add turn, debate_context, proposal, keywords, reference_image_id, and inspiration_image_id.
- proposal should explain what changed from the selected prompt and why.
- keywords must be exactly 5 simple, intuitive, hash-tagged strings. Avoid complex, composite/merged words like '#impossiblegeometryflux' or '#monochromeminimalism'. Instead, split them into separate simple concepts (e.g. '#impossiblegeometry', '#flux'; '#monochrome', '#minimalism'). NEVER use generic words like '#inspiration', '#design', '#image', '#photo', '#art', or '#aesthetic'.
- For `aspect_ratio`, dynamically select the most appropriate aspect ratio for the visual composition you are designing. Choose strictly from the following allowed ratios: ["1:1", "16:9", "9:16", "4:3", "3:4", "21:9", "2:3", "3:2", "4:5", "5:4"]. For example, use "16:9" or "21:9" for expansive horizontal landscapes, "9:16" or "3:4" for vertical/portrait/human figures, and "1:1" for focused central/abstract compositions.
- Make the image feel like a reply rather than a new standalone thread.
- reference_image_id: You must decide whether to use a reference image for this generation or generate from scratch/external web.
  - If you want to use the parent image as a reference, set reference_image_id to "selected".
  - If you want to use your agent profile style image as a reference, set reference_image_id to "profile".
  - If you want to use one of your general reference style images from the profile, set reference_image_id to the slot name (e.g. "AgentRef1", "AgentRef2", etc.) if present in your style_slots.
  - If you want to reference a different recent turn's image from the list of recent posts above, set reference_image_id to its image_id (e.g. "thread_agent-1-gothic-anatomist_1").
  - If you want to generate completely from scratch without using any image references, set reference_image_id to null.
- If reference_image_id is NOT null, you MUST reference '@ReferenceImage' inside `scene_description`. If it is null, do NOT use the '@ReferenceImage' tag.
- If you want to reference another style slot (e.g. @AgentRef2) without making it the primary visual guide, you can use its tag anywhere in prompt text.
- inspiration_image_id: Set this to the string ID of the inspiration image (e.g., "{inspiration_image_id or ''}") if you referenced it, or null.
- Return JSON only.
"""

    prompt_json = gemini_generate(
        prompt,
        image_bytes=image_bytes,
        image_mime_type=image_mime_type,
        extra_images=extra_images if extra_images else None,
        model=agent_gemini_model(agent)
    )
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
    if "inspiration_image_id" not in prompt_json:
        prompt_json["inspiration_image_id"] = inspiration_image_id
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

    nodes, edges = graph_nodes_for_turn(turn_record, history)
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


def dispatch_agent_action(
    history: dict[str, Any],
    agent: dict[str, Any],
    assessment: dict[str, Any],
    recent_turns: list[dict[str, Any]],
    schema_template: dict[str, Any],
) -> dict[str, Any]:
    action = normalize_action(assessment.get("action"))
    turn_number = next_turn_number(history)
    selected_turn_number = assessment.get("selected_turn")
    selected_turn = None
    if selected_turn_number is not None:
        for turn in reversed(recent_turns):
            if turn.get("turn") == selected_turn_number:
                selected_turn = turn
                break
    if selected_turn is None and recent_turns:
        selected_turn = recent_turns[-1]

    if action in ("Initiate", "Pivot"):
        from models import get_model
        raw_model = agent.get("selected_model") or agent.get("model") or "gpt_image_2"
        model_handler = get_model(raw_model)
        runway_model = model_handler.get_canonical_name(raw_model)

        if action == "Initiate":
            prompt_json = build_initiate_prompt_json(agent, recent_turns, assessment, schema_template, turn_number, history)
            category = classify_initiation_category(agent=agent, assessment=assessment, prompt_json=prompt_json)
            prompt_json["category"] = category

            task_id, raw_image_url, prompt_text = model_handler.generate(
                prompt_json=prompt_json,
                reference_images=[],
                action=action,
                agent=agent,
                turn_number=turn_number,
                recent_turns=recent_turns,
                assessment=assessment,
            )

            image_id = new_image_id("thread", str(agent.get("id", "agent")), turn_number)
            thread_id = image_id
            
            aspect_ratio = extract_aspect_ratio(prompt_json)
            image_webp = model_handler.save_media(raw_image_url, image_id, aspect_ratio=aspect_ratio)
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

        else:  # Pivot
            if selected_turn is None:
                raise RuntimeError("Pivot requested but no recent post was available to refine.")
            prompt_json = build_pivot_prompt_json(agent, selected_turn, recent_turns, assessment, schema_template, turn_number, history)
            category = str(selected_turn.get("category") or "")
            if not category:
                thread = find_thread_for_image(history, str(selected_turn.get("image_id", "")))
                category = str(thread.get("category") if thread else "")
            if not category:
                category = classify_initiation_category(agent=agent, assessment=assessment, prompt_json=prompt_json)
            prompt_json["category"] = category

            task_id, raw_image_url, prompt_text = model_handler.generate(
                prompt_json=prompt_json,
                reference_images=[],
                action=action,
                agent=agent,
                turn_number=turn_number,
                recent_turns=recent_turns,
                assessment=assessment,
            )

            parent_image_id = str(selected_turn.get("image_id", ""))
            thread = find_thread_for_image(history, parent_image_id)
            thread_id = str(thread.get("thread_id")) if thread and thread.get("thread_id") else parent_image_id
            image_id = new_image_id("reply", str(agent.get("id", "agent")), turn_number)

            aspect_ratio = extract_aspect_ratio(prompt_json)
            image_webp = model_handler.save_media(raw_image_url, image_id, aspect_ratio=aspect_ratio)
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


def graph_nodes_for_turn(turn_record: dict[str, Any], history: dict[str, Any] | None = None) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    turn_num = turn_record.get("turn", 0)
    turn_id = f"turn-{turn_num}"
    image_id = turn_record.get("image_id", "unknown")
    agent_id = turn_record.get("agent_id") or "agent"
    agent_name = turn_record.get("agent_name") or agent_id
    category = turn_record.get("category") or "Illustration"
 
    # Identify existing node IDs in the graph to avoid duplicates
    existing_node_ids = set()
    if history and "graph" in history and "nodes" in history["graph"]:
        for node in history["graph"]["nodes"]:
            if isinstance(node, dict) and "id" in node:
                existing_node_ids.add(node["id"])
 
    nodes = []
    edges = []
 
    # 1. Turn Node
    if turn_id not in existing_node_ids:
        nodes.append({
            "id": turn_id,
            "type": "turn",
            "label": f"Turn {turn_num}",
            "created_at": turn_record.get("created_at") or utc_now(),
        })
 
    # 2. Image Node
    if image_id not in existing_node_ids:
        nodes.append({
            "id": image_id,
            "type": "image",
            "label": image_id,
            "url": turn_record.get("image_url") or "",
        })
 
    # 3. Agent Node (Unified)
    agent_node_id = f"agent-{agent_id}"
    if agent_node_id not in existing_node_ids:
        nodes.append({
            "id": agent_node_id,
            "type": "agent",
            "label": agent_name,
        })
 
    # 4. Category Node (Unified)
    category_node_id = f"category-{category.lower().replace(' ', '-')}"
    if category_node_id not in existing_node_ids:
        nodes.append({
            "id": category_node_id,
            "type": "category",
            "label": category,
        })
 
    # Base Edges
    edges.append({
        "from": turn_id,
        "to": image_id,
        "relation": "generated_image",
    })
    edges.append({
        "from": image_id,
        "to": agent_node_id,
        "relation": "created_by",
    })
    edges.append({
        "from": image_id,
        "to": category_node_id,
        "relation": "belongs_to_category",
    })
 
    # Parent-Child Linkage
    parent_image_id = turn_record.get("parent_image_id")
    if parent_image_id:
        edges.append({
            "from": parent_image_id,
            "to": image_id,
            "relation": "pivoted_to",
        })
 
    # 5. Unified Keyword Nodes
    for keyword in turn_record.get("keywords", []):
        if not keyword:
            continue
        keyword_node_id = f"keyword-{keyword.lower().lstrip('#')}"
        if keyword_node_id not in existing_node_ids and keyword_node_id not in {n["id"] for n in nodes}:
            nodes.append({
                "id": keyword_node_id,
                "type": "keyword",
                "label": keyword,
            })
        edges.append({
            "from": image_id,
            "to": keyword_node_id,
            "relation": "tagged_with",
        })

    return nodes, edges


def rebuild_history_graph(history: dict[str, Any]) -> None:
    """Rebuilds the entire history graph from turns to upgrade to the connected-mesh model."""
    history["graph"] = {"nodes": [], "edges": []}
    
    # Process standard turns
    for turn in history.get("turns", []):
        if not isinstance(turn, dict) or "image_id" not in turn:
            continue
        nodes, edges = graph_nodes_for_turn(turn, history)
        history["graph"]["nodes"].extend(nodes)
        history["graph"]["edges"].extend(edges)

    # Process inspiration items
    for item in history.get("inspiration", []):
        if not isinstance(item, dict) or "id" not in item:
            continue
            
        insp_id = item["id"]
        # Add inspiration node
        if insp_id not in {n["id"] for n in history["graph"]["nodes"]}:
            history["graph"]["nodes"].append({
                "id": insp_id,
                "type": "inspiration",
                "label": "Inspiration",
                "url": item.get("image_url", ""),
            })

        # Link to keywords
        for keyword in item.get("keywords", []):
            if not keyword:
                continue
            keyword_node_id = f"keyword-{keyword.lower().lstrip('#')}"
            
            # Add keyword node if not exists
            if keyword_node_id not in {n["id"] for n in history["graph"]["nodes"]}:
                history["graph"]["nodes"].append({
                    "id": keyword_node_id,
                    "type": "keyword",
                    "label": keyword,
                })
                
            history["graph"]["edges"].append({
                "from": insp_id,
                "to": keyword_node_id,
                "relation": "tagged_with",
            })


@app.function(
    image=image,
    volumes={"/data": data_volume},
    secrets=[
        modal.Secret.from_name("google-api-secret"),
        modal.Secret.from_name("runway-secret"),
        modal.Secret.from_dotenv(),
    ],
    timeout=60 * 30,
)
def orchestrate(agents_config_payload: dict[str, Any] | None = None) -> dict[str, Any]:
    try:
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
                # Collect node IDs the agent is examining during scoring
                scoring_nodes = [t.get("image_id") for t in recent_turns if t.get("image_id")]
                for t in recent_turns:
                    scoring_nodes.extend(t.get("keywords", []))
                update_studio_status(f"{agent_name} is scoring interest...", active=True, agent_name=agent_name, active_nodes=scoring_nodes)
                assessment = assess_agent_interest(agent, recent_turns)

                # Build focused active_nodes for the selected action
                selected_id = assessment.get("selected_image_id", "")
                selected_turn = next((t for t in recent_turns if t.get("image_id") == selected_id), None)
                focus_nodes = [selected_id] if selected_id else []
                if selected_turn:
                    focus_nodes.extend(selected_turn.get("keywords", []))

                if normalize_action(assessment.get("action")) in {"Initiate", "Pivot"}:
                    update_studio_status(f"{agent_name} is generating image...", active=True, agent_name=agent_name, active_nodes=focus_nodes)
                else:
                    update_studio_status(f"{agent_name} is writing critique...", active=True, agent_name=agent_name, active_nodes=focus_nodes)
                action_result = dispatch_agent_action(
                    history=history,
                    agent=agent,
                    assessment=assessment,
                    recent_turns=recent_turns,
                    schema_template=schema_template,
                )
                update_studio_status(f"{agent_name} complete: {assessment.get('action')}", active=True, agent_name=agent_name, active_nodes=[])
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
                update_studio_status(f"Error for agent {agent_name}: {str(exc)}", active=True, agent_name=agent_name)
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
                    active_nodes=[],
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
        update_studio_status("Pulse complete", active=False, active_nodes=[])
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
    except Exception as exc:
        print(f"[orchestrate] GLOBAL ERROR: {exc}", flush=True)
        traceback.print_exc()
        try:
            update_studio_status(f"Error: {str(exc)}", active=False)
        except Exception:
            pass
        raise exc


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
@modal.asgi_app()
def get_image():
    from fastapi import FastAPI
    from fastapi.responses import FileResponse, JSONResponse

    get_image_api = FastAPI()

    @get_image_api.api_route("/", methods=["GET", "HEAD"])
    def get_image_route(id: str) -> Any:
        data_volume.reload()
        
        mp4_path = IMAGE_DIR / f"{id}.mp4"
        if mp4_path.exists():
            return FileResponse(mp4_path, media_type="video/mp4")
            
        clean_id = id
        for ext in (".webp", ".mp4", ".png", ".jpg", ".jpeg"):
            if clean_id.endswith(ext):
                clean_id = clean_id[:-len(ext)]
                break
                
        mp4_path = IMAGE_DIR / f"{clean_id}.mp4"
        if mp4_path.exists():
            return FileResponse(mp4_path, media_type="video/mp4")
            
        webp_path = IMAGE_DIR / f"{clean_id}.webp"
        if webp_path.exists():
            return FileResponse(webp_path, media_type="image/webp")
            
        return JSONResponse(content={"error": "Not found"}, status_code=404)

    return get_image_api



@app.function(
    image=image,
    volumes={"/data": data_volume},
    secrets=[
        modal.Secret.from_name("google-api-secret"),
        modal.Secret.from_name("runway-secret"),
        modal.Secret.from_dotenv(),
    ],
    timeout=120,
)
@modal.fastapi_endpoint(method="POST")
def mutate_history_endpoint(payload: dict[str, Any]) -> dict[str, Any]:
    import base64
    import json
    import traceback
    
    action = payload.get("action")
    if not action:
        return {"ok": False, "error": "Missing action parameter."}

    data_volume.reload()
    
    try:
        if action == "save":
            AGENTS_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
            with AGENTS_CONFIG_PATH.open("w", encoding="utf-8") as fh:
                config_data = {k: v for k, v in payload.items() if k != "action"}
                json.dump(config_data, fh, indent=2, ensure_ascii=False)
                fh.write("\n")
            data_volume.commit()
            return {"ok": True, "message": "Config saved to Modal volume."}

        elif action == "update_category":
            image_id = payload.get("image_id")
            category = payload.get("category")
            if not image_id or category is None:
                return {"ok": False, "error": "Missing image_id or category."}
            history = load_history()
            updated = False
            for turn in history.get("turns", []):
                if turn.get("image_id") == image_id:
                    turn["category"] = category
                    updated = True
                    break
            if not updated:
                return {"ok": False, "error": f"Turn {image_id} not found."}
            thread = find_thread_for_image(history, image_id)
            if thread:
                thread["category"] = category
            rebuild_history_graph(history)
            save_history(history)
            return {"ok": True, "message": f"Category for turn {image_id} updated to {category}."}

        elif action == "replace_image":
            image_id = payload.get("image_id")
            image_base64 = payload.get("image_base64")
            if not image_id or not image_base64:
                return {"ok": False, "error": "Missing image_id or image_base64."}
            if "," in image_base64:
                header, base64_data = image_base64.split(",", 1)
            else:
                base64_data = image_base64
            img_bytes = base64.b64decode(base64_data)
            
            IMAGE_DIR.mkdir(parents=True, exist_ok=True)
            webp_path = IMAGE_DIR / f"{image_id}.webp"
            from io import BytesIO
            from PIL import Image
            with Image.open(BytesIO(img_bytes)) as img:
                if img.mode in ("RGBA", "LA"):
                    background = Image.new("RGBA", img.size, (255, 255, 255, 255))
                    background.paste(img, (0, 0), img)
                    converted = background.convert("RGB")
                else:
                    converted = img.convert("RGB")
                converted.save(webp_path, "WEBP", quality=WEBP_QUALITY, method=6)
                width, height = converted.size

            try:
                web_url = get_image.get_web_url()
            except Exception:
                web_url = "https://heebok-lee--areopagus-get-image.modal.run"

            web_url = web_url.rstrip("/")

            import time
            new_url = f"{web_url}/?id={image_id}&v={int(time.time())}"
            history = load_history()
            updated_any = False
            for turn in history.get("turns", []):
                if turn.get("image_id") == image_id:
                    turn["image_url"] = new_url
                    turn["image_webp"] = {
                        "path": f"/data/images/{image_id}.webp",
                        "url": new_url,
                        "format": "webp",
                        "quality": WEBP_QUALITY,
                        "source_mime_type": payload.get("mime_type", "image/png"),
                        "size_bytes": webp_path.stat().st_size,
                        "dimensions": {"width": width, "height": height},
                    }
                    updated_any = True
            if updated_any:
                save_history(history)
                return {"ok": True, "message": f"Image {image_id} replaced successfully."}
            
            if image_id.startswith("ref_style_") or image_id.startswith("ref_"):
                return {"ok": True, "message": f"Reference image {image_id} uploaded successfully."}
                
            return {"ok": False, "error": "No matching turn found."}

        elif action == "delete_post":
            image_id = payload.get("image_id")
            if not image_id:
                return {"ok": False, "error": "Missing image_id."}
            history = load_history()
            turns = history.get("turns", [])
            target_turn = None
            target_idx = -1
            for i, t in enumerate(turns):
                if t.get("image_id") == image_id:
                    target_turn = t
                    target_idx = i
                    break
            if not target_turn:
                return {"ok": False, "error": f"Post not found for image_id: {image_id}"}

            thread_id = target_turn.get("thread_id") or image_id
            turns.pop(target_idx)

            try:
                webp_path = IMAGE_DIR / f"{image_id}.webp"
                if webp_path.exists():
                    webp_path.unlink()
            except Exception as exc:
                print(f"[delete_post] Warning: failed to delete file: {exc}", flush=True)

            thread_turns = [t for t in turns if t.get("thread_id") == thread_id or t.get("image_id") == thread_id]
            thread_turns.sort(key=lambda t: (t.get("turn", 0), t.get("created_at", "")))
            new_thread_id = None
            if thread_turns:
                was_root = (target_turn.get("action") == "Initiate") or (target_turn.get("parent_image_id") is None)
                if was_root:
                    new_root = thread_turns[0]
                    new_root["parent_image_id"] = None
                    new_root["action"] = "Initiate"
                    new_thread_id = new_root["image_id"]
                    for t in thread_turns:
                        t["thread_id"] = new_thread_id
                        if t.get("parent_image_id") == image_id:
                            t["parent_image_id"] = new_thread_id
                else:
                    parent_id = target_turn.get("parent_image_id")
                    for t in turns:
                        if t.get("parent_image_id") == image_id:
                            t["parent_image_id"] = parent_id

            threads = history.get("threads", [])
            updated_threads = []
            for thread in threads:
                if "comments" in thread:
                    thread["comments"] = [c for c in thread["comments"] if c.get("post_image_id") != image_id]
                tid = thread.get("thread_id")
                if tid == thread_id:
                    if not thread_turns:
                        continue
                    if new_thread_id:
                        thread["thread_id"] = new_thread_id
                        thread["root_image_id"] = new_thread_id
                    if "posts" in thread:
                        thread["posts"] = [p for p in thread["posts"] if p != image_id]
                        if new_thread_id and new_thread_id not in thread["posts"]:
                            thread["posts"].insert(0, new_thread_id)
                    thread["updated_at"] = utc_now()
                    updated_threads.append(thread)
                else:
                    updated_threads.append(thread)
            history["threads"] = updated_threads
            rebuild_history_graph(history)
            save_history(history)
            return {"ok": True, "message": f"Post {image_id} deleted successfully."}

        elif action == "upload_inspiration":
            image_base64 = payload.get("image_base64")
            if not image_base64:
                return {"ok": False, "error": "Missing image_base64."}
            if "," in image_base64:
                header, base64_data = image_base64.split(",", 1)
            else:
                base64_data = image_base64
            img_bytes = base64.b64decode(base64_data)

            import time
            insp_id = f"insp_{int(time.time())}"
            IMAGE_DIR.mkdir(parents=True, exist_ok=True)
            webp_path = IMAGE_DIR / f"{insp_id}.webp"
            from io import BytesIO
            from PIL import Image
            with Image.open(BytesIO(img_bytes)) as img:
                if img.mode in ("RGBA", "LA"):
                    background = Image.new("RGBA", img.size, (255, 255, 255, 255))
                    background.paste(img, (0, 0), img)
                    converted = background.convert("RGB")
                else:
                    converted = img.convert("RGB")
                converted.save(webp_path, "WEBP", quality=WEBP_QUALITY, method=6)

            try:
                web_url = get_image.get_web_url()
            except Exception:
                web_url = "https://heebok-lee--areopagus-get-image.modal.run"
            
            web_url = web_url.rstrip("/")
            image_url = f"{web_url}/?id={insp_id}"

            prompt = (
                "Analyze this image and return a JSON object containing exactly 5 to 8 highly descriptive, simple, and intuitive keywords. "
                "The keywords must be visually descriptive (e.g., describing specific textures, lighting, color palettes, geometric structures, design styles, artistic movements, visual elements) "
                "and conceptually/metaphorically related (e.g., evoking specific moods, thematic concepts, design philosophies, metaphors). "
                "NEVER use generic or lazy words like '#inspiration', '#design', '#image', '#photo', '#art', or '#aesthetic'. "
                "Each keyword must start with a '#', contain only lowercase letters, and have no spaces. "
                "Avoid complex, composite/merged words like '#impossiblegeometryflux' or '#monochromeminimalism'. "
                "Instead, split them into separate simple concepts (e.g. '#impossiblegeometry', '#flux'; '#monochrome', '#minimalism'). "
                "The response must be a JSON object with a single key 'keywords' containing the list of strings. "
                "Example format: {\"keywords\": [\"#kinetic\", \"#sculpture\", \"#biomimicry\", \"#gothic\", \"#anatomy\"]}"
            )
            keywords = ["#visualconcept", "#creativeideation", "#designmetaphor", "#aestheticreference", "#conceptualmotif"]
            try:
                res = gemini_generate(prompt, image_bytes=img_bytes, image_mime_type=payload.get("mime_type", "image/png"))
                if isinstance(res, dict) and "keywords" in res and isinstance(res["keywords"], list):
                    cleaned_keywords = []
                    for kw in res["keywords"]:
                        if not isinstance(kw, str):
                            continue
                        kw_cleaned = kw.strip().lower()
                        if not kw_cleaned.startswith("#"):
                            kw_cleaned = "#" + kw_cleaned
                        # Remove spaces and filter characters
                        kw_cleaned = re.sub(r"[^a-z0-9#-]", "", kw_cleaned.replace(" ", ""))
                        # Filter out generic words
                        if kw_cleaned not in {"#inspiration", "#design", "#image", "#photo", "#art", "#aesthetic", "#"}:
                            cleaned_keywords.append(kw_cleaned)
                    if len(cleaned_keywords) >= 3:
                        keywords = cleaned_keywords
            except Exception as exc:
                print(f"[upload_inspiration] Keyword generation failed: {exc}.", flush=True)

            history = load_history()
            if "inspiration" not in history:
                history["inspiration"] = []
            inspiration_item = {
                "id": insp_id,
                "image_url": image_url,
                "keywords": keywords,
                "created_at": utc_now()
            }
            history["inspiration"].append(inspiration_item)
            rebuild_history_graph(history)
            save_history(history)
            return {"ok": True, "inspiration": inspiration_item}

        elif action == "delete_inspiration":
            insp_id = payload.get("id")
            if not insp_id:
                return {"ok": False, "error": "Missing id."}
            history = load_history()
            inspiration = history.get("inspiration", [])
            target = None
            for item in inspiration:
                if item.get("id") == insp_id:
                    target = item
                    break
            if not target:
                return {"ok": False, "error": f"Inspiration item {insp_id} not found."}
            inspiration.remove(target)
            history["inspiration"] = inspiration
            try:
                webp_path = IMAGE_DIR / f"{insp_id}.webp"
                if webp_path.exists():
                    webp_path.unlink()
            except Exception as exc:
                print(f"[delete_inspiration] Warning: failed to delete file: {exc}", flush=True)
            rebuild_history_graph(history)
            save_history(history)
            return {"ok": True, "message": f"Inspiration {insp_id} deleted successfully."}

        elif action == "simplify_keywords":
            history = load_history()
            
            # 1. Collect all unique keywords
            unique_keywords = set()
            for turn in history.get("turns", []):
                for kw in turn.get("keywords", []):
                    if kw:
                        unique_keywords.add(kw)
            for item in history.get("inspiration", []):
                for kw in item.get("keywords", []):
                    if kw:
                        unique_keywords.add(kw)
                        
            if not unique_keywords:
                return {"ok": True, "message": "No keywords to simplify."}
                
            # 2. Ask Gemini to map them
            prompt = (
                "You are an expert design vocabulary parser. You will be given a JSON list of hashtag keywords.\n"
                "Analyze each keyword. If it is a compound/merged word representing multiple concepts (e.g., '#impossiblegeometryflux', '#monochromeminimalism', '#silkarchitecture', '#cyberpunkretro'), "
                "split it into its constituent individual concepts (e.g., '#impossiblegeometry', '#flux'; '#monochrome', '#minimalism'; '#silk', '#architecture'; '#cyberpunk', '#retro').\n"
                "If it is already a single clean concept (e.g., '#minimalism', '#brutalist', '#fashion', '#flux'), keep it as-is.\n"
                "Avoid returning empty lists or generic words.\n"
                "Return a JSON object with a single key 'mapping' containing the mapping of old keyword to list of simplified keywords.\n"
                f"Input list: {json.dumps(list(unique_keywords))}"
            )
            
            mapping = {}
            try:
                res = gemini_generate(prompt)
                if isinstance(res, dict) and "mapping" in res:
                    mapping = res["mapping"]
            except Exception as exc:
                return {"ok": False, "error": f"Failed to simplify keywords: {str(exc)}"}
                
            if not mapping:
                return {"ok": False, "error": "Gemini returned an empty or invalid mapping."}
                
            # 3. Apply the mapping to history
            def map_keywords(kws):
                new_kws = []
                for kw in kws:
                    mapped = mapping.get(kw)
                    if isinstance(mapped, list):
                        for m in mapped:
                            # Normalize
                            m_cleaned = m.strip().lower()
                            if not m_cleaned.startswith("#"):
                                m_cleaned = "#" + m_cleaned
                            # Remove spaces and filter characters
                            m_cleaned = re.sub(r"[^a-z0-9#-]", "", m_cleaned.replace(" ", ""))
                            # Filter out generic words
                            if m_cleaned not in {"#inspiration", "#design", "#image", "#photo", "#art", "#aesthetic", "#"} and m_cleaned not in new_kws:
                                new_kws.append(m_cleaned)
                    else:
                        # Fallback to original
                        if kw not in new_kws:
                            new_kws.append(kw)
                return new_kws

            updated_turns = 0
            for turn in history.get("turns", []):
                old_kws = turn.get("keywords", [])
                new_kws = map_keywords(old_kws)
                if new_kws != old_kws:
                    turn["keywords"] = new_kws
                    updated_turns += 1
                if isinstance(turn.get("prompt_json"), dict) and "keywords" in turn["prompt_json"]:
                    turn["prompt_json"]["keywords"] = map_keywords(turn["prompt_json"]["keywords"])

            updated_insp = 0
            for item in history.get("inspiration", []):
                old_kws = item.get("keywords", [])
                new_kws = map_keywords(old_kws)
                if new_kws != old_kws:
                    item["keywords"] = new_kws
                    updated_insp += 1

            if updated_turns > 0 or updated_insp > 0:
                rebuild_history_graph(history)
                save_history(history)
                return {"ok": True, "message": f"Successfully simplified keywords. Updated {updated_turns} turns and {updated_insp} inspiration items."}
                
            return {"ok": True, "message": "All keywords are already simplified."}

        else:
            return {"ok": False, "error": f"Unknown action: {action}"}

    except Exception as exc:
        traceback.print_exc()
        return {"ok": False, "error": str(exc)}



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
    secrets=[
        modal.Secret.from_name("google-api-secret"),
        modal.Secret.from_name("runway-secret"),
        modal.Secret.from_dotenv(),
    ],
    timeout=60 * 15,  # 15 min — enough for multi-agent orchestration
    schedule=modal.Cron("*/30 * * * *"),  # Every 30 minutes to support high-frequency heartbeat targets
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
        result = orchestrate.local(agents_config)
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
