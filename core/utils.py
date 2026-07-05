import os
import re
import json
import random
import uuid
import time
import traceback
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple

from core.config import (
    ROOT_PATH,
    SCHEMA_PATH,
    LOCAL_AGENTS_CONFIG_PATH,
    AGENTS_CONFIG_PATH,
    DATA_DIR,
    KEYWORD_COUNT,
    RUNWAY_SAFETY_REPLACEMENTS,
    GEMINI_MODEL,
    RUNWAY_RATIO_BY_MODEL,
    DEFAULT_AGENT_ACTIONS,
    INTEREST_WINDOW,
)

def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_schema_template() -> dict[str, Any]:
    raw = SCHEMA_PATH.read_text(encoding="utf-8")
    raw = raw.replace("\ufeff", "").replace("\u00a0", " ")
    return json.loads(raw)


def load_agents_config(override: dict[str, Any] | None = None, commit_callback: Any | None = None) -> dict[str, Any]:
    if isinstance(override, dict):
        override.setdefault("agents", [])
        return override

    local_config = None
    if LOCAL_AGENTS_CONFIG_PATH.exists():
        try:
            with LOCAL_AGENTS_CONFIG_PATH.open("r", encoding="utf-8") as fh:
                local_config = json.load(fh)
        except Exception as e:
            print(f"[load_agents_config] Error reading local config: {e}", flush=True)

    volume_config = None
    if AGENTS_CONFIG_PATH.exists():
        try:
            with AGENTS_CONFIG_PATH.open("r", encoding="utf-8") as fh:
                volume_config = json.load(fh)
        except Exception as e:
            print(f"[load_agents_config] Error reading volume config: {e}", flush=True)

    # Reconcile local repository config with persistent volume config
    config = None
    if local_config:
        local_agents = {a.get("name") for a in local_config.get("agents", []) if a.get("name")}
        volume_agents = {a.get("name") for a in volume_config.get("agents", []) if a.get("name")} if volume_config else set()
        
        # Check if local config has a newer updated_at timestamp
        local_updated = local_config.get("updated_at", "")
        volume_updated = volume_config.get("updated_at", "") if volume_config else ""
        is_newer = False
        if local_updated and volume_updated:
            try:
                if local_updated > volume_updated:
                    is_newer = True
            except Exception:
                pass

        # If volume is missing, holds completely different agents, or local config is newer, overwrite/seed
        if not volume_config or local_agents != volume_agents or is_newer:
            print(f"[load_agents_config] Overwriting/Seeding volume config with local config", flush=True)
            config = local_config
            try:
                AGENTS_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
                with AGENTS_CONFIG_PATH.open("w", encoding="utf-8") as fh:
                    json.dump(config, fh, indent=2, ensure_ascii=False)
                    fh.write("\n")
                if commit_callback is not None:
                    try:
                        commit_callback()
                    except Exception as commit_err:
                        print(f"[load_agents_config] Error invoking commit_callback: {commit_err}", flush=True)
            except Exception as e:
                print(f"[load_agents_config] Error updating volume config: {e}", flush=True)
        else:
            config = volume_config
    elif volume_config:
        config = volume_config
    else:
        config = {"agents": []}

    config.setdefault("agents", [])
    return config


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


def kie_api_key() -> str:
    return os.environ.get("KIE_API_KEY", "").strip()


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


def remove_reference_tags(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: remove_reference_tags(item) for key, item in value.items()}
    if isinstance(value, list):
        return [remove_reference_tags(item) for item in value]
    if isinstance(value, str):
        text = re.sub(r"@ReferenceImage\b", "", value)
        text = re.sub(r"@AgentRef\d+\b", "", text)
        text = re.sub(r"\s+", " ", text).strip()
        # Clean up any stray commas/punctuation that were right next to the tags
        text = re.sub(r",\s*,", ",", text)
        text = re.sub(r"\s+,\s+", ", ", text)
        text = re.sub(r"\s+\.\s+", ". ", text)
        text = text.replace("inspired by but", "inspired by")
        text = text.replace("inspired by ,", "")
        text = text.replace("inspired by .", "")
        text = re.sub(r"\s+", " ", text).strip()
        return text
    return value


def agent_gemini_model(agent: dict[str, Any]) -> str:
    gemini_model = agent.get("gemini_model")
    if isinstance(gemini_model, str) and gemini_model.strip():
        return gemini_model.strip()

    model_name = str(agent.get("model", "")).strip().lower()
    if "gemini" in model_name:
        return "gemini-2.5-flash"

    return GEMINI_MODEL


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


def clamp_interest_score(value: Any) -> int:
    try:
        score = int(round(float(value)))
    except (TypeError, ValueError):
        score = 0
    return max(0, min(100, score))
