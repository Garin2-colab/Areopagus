import json
import uuid
import re
from datetime import datetime, timezone
from typing import Any

import random
from core.config import (
    DATA_DIR,
    HISTORY_PATH,
    PENDING_TASKS_PATH,
    HEARTBEAT_PATH,
    STUDIO_STATUS_PATH,
)
from core.utils import (
    utc_now,
    get_active_agents,
    clamp_interest_score,
    summarize_turn_for_agent,
    agent_gemini_model,
    normalize_action,
)
from core.gemini import gemini_generate
from core.graph import rebuild_history_graph

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
        try:
            from orchestrator import data_volume
            data_volume.commit()
        except Exception:
            pass
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
        try:
            from orchestrator import data_volume
            data_volume.commit()
        except Exception:
            pass

    return history


def save_history(history: dict[str, Any]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    history["updated_at"] = utc_now()
    with HISTORY_PATH.open("w", encoding="utf-8") as fh:
        json.dump(history, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    try:
        from orchestrator import data_volume
        data_volume.commit()
    except Exception:
        pass


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
    try:
        from orchestrator import data_volume
        data_volume.commit()
    except Exception:
        pass


def remove_pending_task(task_id: str) -> dict[str, Any] | None:
    tasks = load_pending_tasks()
    task = tasks.pop(task_id, None)
    if task:
        with PENDING_TASKS_PATH.open("w", encoding="utf-8") as fh:
            json.dump(tasks, fh, indent=2, ensure_ascii=False)
        try:
            from orchestrator import data_volume
            data_volume.commit()
        except Exception:
            pass
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
    try:
        from orchestrator import data_volume
        data_volume.commit()
    except Exception:
        pass
    return status


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

    # Search Second Brain items (highest priority)
    for brain_item in history.get("brain", []):
        if not isinstance(brain_item, dict) or "id" not in brain_item:
            continue

        brain_keywords = {k.lower() for k in brain_item.get("keywords", [])}
        overlap = brain_keywords.intersection(current_keywords_set)
        if overlap:
            brain_copy = dict(brain_item)
            brain_copy["image_id"] = brain_item["id"]
            brain_copy["turn"] = "Brain"
            brain_copy["proposal"] = brain_item.get("summary", "Second Brain Reference")
            # Assign highest priority to brain items
            candidates.append((len(overlap), 10000, brain_copy))

    if not candidates:
        return None

    # Sort candidates by overlap descending, then by turn/relevance descending
    candidates.sort(key=lambda x: (x[0], x[1]), reverse=True)
    return candidates[0][2]


def read_heartbeat_state() -> dict[str, Any]:
    """Load the last heartbeat timestamp from volume."""
    if HEARTBEAT_PATH.exists():
        with HEARTBEAT_PATH.open("r", encoding="utf-8") as fh:
            return json.load(fh)
    return {}


def write_heartbeat_state(state: dict[str, Any]) -> None:
    """Persist heartbeat state to volume."""
    HEARTBEAT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with HEARTBEAT_PATH.open("w", encoding="utf-8") as fh:
        json.dump(state, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    try:
        from orchestrator import data_volume
        data_volume.commit()
    except Exception:
        pass


def max_heartbeat_frequency(agents_config: dict[str, Any]) -> int:
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


def heartbeat_interval_seconds(times_per_day: int) -> float:
    """Convert N-times-per-day to the minimum interval in seconds between pulses."""
    if times_per_day <= 0:
        return float("inf")
    return (24 * 3600) / times_per_day


def is_agent_allowed_to_reply(agent_id: str, thread_id: str, history: dict[str, Any]) -> bool:
    # Find who initiated this thread.
    initiator_agent_id = None
    for turn in history.get("turns", []):
        if turn.get("thread_id") == thread_id and turn.get("action") == "Initiate":
            initiator_agent_id = turn.get("agent_id")
            break
            
    if not initiator_agent_id:
        # Fallback: look at the first turn of this thread by turn number
        thread_turns = [t for t in history.get("turns", []) if t.get("thread_id") == thread_id]
        if thread_turns:
            first_turn = min(thread_turns, key=lambda t: t.get("turn", 9999))
            initiator_agent_id = first_turn.get("agent_id")
            
    # If the current agent is NOT the initiator, they are always allowed to reply
    if initiator_agent_id != agent_id:
        return True
        
    # If the current agent IS the initiator, they can only reply if there's at least one turn or comment from another agent
    # Check other agent's turns in this thread:
    has_other_turn = any(
        turn.get("agent_id") != agent_id 
        for turn in history.get("turns", []) 
        if turn.get("thread_id") == thread_id
    )
    if has_other_turn:
        return True
        
    # Check other agent's comments in this thread:
    thread = find_thread(history, thread_id)
    if thread:
        has_other_comment = any(
            comment.get("agent_id") != agent_id 
            for comment in thread.get("comments", [])
        )
        if has_other_comment:
            return True
            
    return False


def assess_agent_interest(agent: dict[str, Any], recent_turns: list[dict[str, Any]], history: dict[str, Any] = None) -> dict[str, Any]:
    if history is None:
        history = load_history()

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
- Align the action selection closely with the agent's persona instructions. For example, if the persona starts with or contains instructions like "Generate a new image based on these" or emphasizes producing designs/images, you MUST choose "Pivot" (replacing with a new image) or "Initiate" (starting a new thread with a new image) as the action, rather than "Critique" (text comment).
- For each of the recent posts, give an `interest_score` from 0 to 100. If a post is highly relevant, score it high. If it is mundane or irrelevant to their aesthetics, score it low.
- To act like a human, be highly selective: agents do not react to everything. An interest score below 50 means they will ignore it.
- For each post, decide the best reply `action` if the agent were to reply:
  - Use `Pivot` when the agent wants to reply by generating a new image inspired by the post.
  - Use `Critique` when the agent wants to reply with text only (commenting).
- Crucial rule for conversation flow: An agent is NOT allowed to reply (neither Critique nor Pivot) to a thread that they themselves initiated, UNLESS another agent has already replied/commented in that thread. If the agent initiated the thread and no one else has commented on it yet, you must score interest for all posts in that thread as 0.
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
        
        # Enforce thread initiator permission rule
        image_id = score.get("image_id")
        action_val = normalize_action(score.get("action"))
        reason_val = score.get("reason", "")
        
        if image_id:
            thread = find_thread_for_image(history, image_id)
            if thread:
                tid = thread.get("thread_id")
                if not is_agent_allowed_to_reply(agent.get("id"), tid, history):
                    jittered_score = 0
                    action_val = "Initiate"
                    reason_val = f"[Restricted] Cannot comment or pivot on own initiated thread '{tid}' until another agent comments."

        normalized_scores.append(
            {
                "turn": score.get("turn"),
                "image_id": image_id,
                "interest_score": jittered_score,
                "action": action_val,
                "reason": reason_val,
            }
        )

    # 15% probability of a pure whim/impulse override
    is_whim = random.random() < 0.15
    best_post_score = max(normalized_scores, key=lambda item: item["interest_score"]) if normalized_scores else None

    if is_whim and normalized_scores:
        # Flip a coin: either initiate a new thread, or reply to an allowed random post
        whim_choice = random.choice(["initiate", "reply"])
        if whim_choice == "initiate":
            assessment["selected_turn"] = None
            assessment["selected_image_id"] = ""
            assessment["interest_score"] = initiate_score
            assessment["action"] = "Initiate"
            assessment["reason"] = f"[Whim] A sudden spark of inspiration led {agent.get('name')} to start a new thread."
            print(f"[orchestrate] WHIM: {agent.get('name')} chose to INITIATE a new thread on a whim.", flush=True)
        else:
            allowed_posts = [p for p in normalized_scores if p.get("interest_score", 0) >= 50]
            if allowed_posts:
                random_post = random.choice(allowed_posts)
                assessment["selected_turn"] = random_post.get("turn")
                assessment["selected_image_id"] = random_post.get("image_id")
                assessment["interest_score"] = random_post["interest_score"]
                assessment["action"] = random_post["action"]
                assessment["reason"] = f"[Whim] A passing detail caught {agent.get('name')}'s eye, compelling them to react: {random_post.get('reason')}"
                print(f"[orchestrate] WHIM: {agent.get('name')} chose to interact with Turn {random_post.get('turn')} on a whim.", flush=True)
            else:
                assessment["selected_turn"] = None
                assessment["selected_image_id"] = ""
                assessment["interest_score"] = initiate_score
                assessment["action"] = "Initiate"
                assessment["reason"] = f"[Whim Fallback] {agent.get('name')} initiated a new thread since no other interesting posts were available."
                print(f"[orchestrate] WHIM: {agent.get('name')} chose to INITIATE (fallback) on a whim.", flush=True)
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
