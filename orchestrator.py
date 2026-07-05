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
try:
    from fastapi import Request
except ImportError:
    class Request:
        pass

from core import (
    APP_NAME,
    VOLUME_NAME,
    HISTORY_PATH,
    AGENTS_CONFIG_PATH,
    STUDIO_STATUS_PATH,
    HEARTBEAT_PATH,
    IMAGE_DIR,
    SCHEMA_PATH,
    
    # Constants
    INTEREST_WINDOW,
    PULSE_JITTER_MIN_SECONDS,
    PULSE_JITTER_MAX_SECONDS,
    WEBP_QUALITY,
    CATEGORY_OPTIONS,
    GEMINI_MODEL,
    
    # Helper functions
    load_schema_template,
    load_history,
    load_agents_config,
    save_history,
    update_studio_status,
    utc_now,
    normalize_action,
    get_active_agents,
    summarize_turn_for_agent,
    recent_turns_for_agents,
    next_turn_number,
    new_image_id,
    ensure_threads,
    find_thread_for_image,
    upsert_thread,
    append_thread_comment,
    assess_agent_interest,
    graph_nodes_for_turn,
    rebuild_history_graph,
    extract_aspect_ratio,
    gemini_generate,
    sanitize_for_runway,
    
    # Heartbeat functions
    read_heartbeat_state,
    write_heartbeat_state,
    max_heartbeat_frequency,
    heartbeat_interval_seconds,
)

# ── Modal Environment Setup ──────────────────────────────────────────────────
app = modal.App(APP_NAME)
data_volume = modal.Volume.from_name(VOLUME_NAME, create_if_missing=True)

image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("ffmpeg")
    .pip_install("pillow", "fastapi[standard]")
    .add_local_dir("./example", remote_path="/root/example")
    .add_local_dir("./models", remote_path="/root/models")
    .add_local_dir("./core", remote_path="/root/core")
    .add_local_file("./prompt_builder.py", remote_path="/root/prompt_builder.py")
    .add_local_file("./agents_config.json", remote_path="/root/agents_config.json")
)


def verify_api_key(request) -> dict[str, Any] | None:
    """Check X-API-Key header or api_key query param. Returns error dict or None if OK."""
    expected = os.environ.get("AREOPAGUS_API_KEY", "").strip()
    if not expected:
        # No key configured — allow all (backwards compatibility during rollout)
        return None
    # Check header first, then query param
    provided = ""
    if hasattr(request, "headers"):
        provided = (request.headers.get("x-api-key") or "").strip()
    if not provided and hasattr(request, "query_params"):
        provided = (request.query_params.get("api_key") or "").strip()
    if provided == expected:
        return None
    return {"ok": False, "error": "Unauthorized. Invalid or missing API key."}


# ── Execution Helpers ─────────────────────────────────────────────────────────

def build_initiate_prompt_json(
    agent: dict[str, Any],
    recent_turns: list[dict[str, Any]],
    assessment: dict[str, Any],
    schema_template: dict[str, Any],
    turn_number: int,
    history: dict[str, Any] | None = None,
) -> dict[str, Any]:
    from prompt_builder import build_initiate_prompt_json as _build_initiate_prompt_json
    return _build_initiate_prompt_json(agent, recent_turns, assessment, schema_template, turn_number, history)


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
    from prompt_builder import build_pivot_prompt_json as _build_pivot_prompt_json
    return _build_pivot_prompt_json(agent, selected_turn, recent_turns, assessment, schema_template, turn_number, history)


def build_comment_json(
    agent: dict[str, Any],
    selected_turn: dict[str, Any],
    assessment: dict[str, Any],
) -> dict[str, Any]:
    from prompt_builder import build_comment_json as _build_comment_json
    return _build_comment_json(agent, selected_turn, assessment)


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
        "inspiration_image_id": prompt_json.get("inspiration_image_id"),
        "inspiration_note_id": prompt_json.get("inspiration_note_id"),
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
    agent_name = agent.get("name", agent.get("id", "Agent"))
    print(f"[dispatch_agent_action] Dispatched action '{action}' for agent '{agent_name}' target_turn={assessment.get('selected_turn')}", flush=True)
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


# ── Modal Entrypoints and Functions ───────────────────────────────────────────

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
        agents_config = load_agents_config(agents_config_payload, commit_callback=data_volume.commit)
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
                assessment = assess_agent_interest(agent, recent_turns, history)
                print(f"[orchestrate] Assessment for '{agent_name}': {json.dumps(assessment, indent=2)}", flush=True)

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
                print(f"[orchestrate] Completed action '{assessment.get('action')}' for agent '{agent_name}'. Result: {json.dumps(action_result, indent=2)}", flush=True)
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
    secrets=[modal.Secret.from_dotenv()],
    timeout=60,
    min_containers=1,
)
@modal.fastapi_endpoint(method="GET")
def history_endpoint(request: Request) -> dict[str, Any]:
    auth_error = verify_api_key(request)
    if auth_error:
        return auth_error
    data_volume.reload()
    history = load_history()
    
    limit = int(request.query_params.get("limit", 0))
    offset = int(request.query_params.get("offset", 0))
    item_type = request.query_params.get("type", "")
    search = request.query_params.get("search", "")
    
    if "brain" in history and isinstance(history["brain"], list):
        brain_list = history["brain"]
        
        # 1. Filter by type
        if item_type:
            req_type = "document" if item_type == "note" else item_type
            brain_list = [item for item in brain_list if item.get("type") == req_type]
            
        # 2. Filter by search
        if search:
            q = search.lower()
            brain_list = [
                item for item in brain_list
                if q in item.get("title", "").lower() or
                   q in item.get("summary", "").lower() or
                   any(q in kw.lower() for kw in item.get("keywords", []))
            ]
            
        total_count = len(brain_list)
        
        # 3. Paginate
        if limit > 0:
            brain_list = brain_list[offset:offset+limit]
            
        history["brain"] = brain_list
        history["total_brain_items"] = total_count
        history["limit"] = limit
        history["offset"] = offset
        
        # Exclude massive arrays to keep pagination response light and fast
        if limit > 0 or offset > 0 or item_type or search:
            history["turns"] = []
            history["threads"] = []
            history["inspiration"] = []
            history["briefs"] = []
            history["graph"] = {"nodes": [], "edges": []}
        
    return history


@app.function(
    image=image,
    volumes={"/data": data_volume},
    secrets=[modal.Secret.from_dotenv()],
    timeout=60,
    min_containers=1,
)
@modal.fastapi_endpoint(method="GET")
def status_endpoint(request: Request) -> dict[str, Any]:
    auth_error = verify_api_key(request)
    if auth_error:
        return auth_error
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
    from fastapi import FastAPI, Request
    from fastapi.responses import FileResponse, JSONResponse, Response
    from fastapi.middleware.cors import CORSMiddleware
    from PIL import Image
    from io import BytesIO

    get_image_api = FastAPI()
    get_image_api.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    def handle_get_image(image_id: str, ext: str = None, format: str = None) -> Any:
        data_volume.reload()
        
        if not image_id:
            return JSONResponse(content={"error": "Missing id parameter"}, status_code=400)
            
        clean_id = image_id
        requested_ext = None
        
        ext_param = ext or format
        if ext_param:
            ext_param = ext_param.strip().lower()
            if not ext_param.startswith("."):
                ext_param = "." + ext_param
            if ext_param in (".webp", ".png", ".jpg", ".jpeg", ".mp4"):
                requested_ext = ext_param
                
        for r_ext in (".webp", ".mp4", ".png", ".jpg", ".jpeg"):
            if clean_id.endswith(r_ext):
                if not requested_ext:
                    requested_ext = r_ext
                clean_id = clean_id[:-len(r_ext)]
                break
                
        # Serve MP4 if explicitly requested, or if no format was specified and mp4 exists
        serve_mp4 = False
        mp4_path = IMAGE_DIR / f"{clean_id}.mp4"
        if mp4_path.exists():
            if requested_ext == ".mp4" or requested_ext is None:
                serve_mp4 = True
                
        if serve_mp4:
            return FileResponse(mp4_path, media_type="video/mp4")
            
        webp_path = IMAGE_DIR / f"{clean_id}.webp"
        if webp_path.exists():
            if requested_ext in (".png", ".jpg", ".jpeg"):
                try:
                    img = Image.open(webp_path)
                    out_buf = BytesIO()
                    
                    if requested_ext == ".png":
                        img.save(out_buf, format="PNG")
                        media_type = "image/png"
                    else:  # .jpg or .jpeg
                        if img.mode in ("RGBA", "LA"):
                            background = Image.new("RGB", img.size, (255, 255, 255))
                            background.paste(img, mask=img.split()[-1] if img.mode == "RGBA" else None)
                            background.save(out_buf, format="JPEG", quality=90)
                        else:
                            img.convert("RGB").save(out_buf, format="JPEG", quality=90)
                        media_type = "image/jpeg"
                        
                    return Response(content=out_buf.getvalue(), media_type=media_type)
                except Exception as exc:
                    print(f"[get_image] On-the-fly conversion failed for {clean_id}: {exc}", flush=True)
                    return FileResponse(webp_path, media_type="image/webp")
            
            return FileResponse(webp_path, media_type="image/webp")
            
        return JSONResponse(content={"error": "Not found"}, status_code=404)

    @get_image_api.api_route("/", methods=["GET", "HEAD"])
    def get_image_query(id: str = None, ext: str = None, format: str = None) -> Any:
        return handle_get_image(id, ext, format)

    @get_image_api.api_route("/{id}", methods=["GET", "HEAD"])
    def get_image_path(id: str, ext: str = None, format: str = None) -> Any:
        return handle_get_image(id, ext, format)

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
@modal.asgi_app()
def mutate_history_endpoint():
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware
    import base64
    import json
    import traceback

    mutate_api = FastAPI()
    mutate_api.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @mutate_api.middleware("http")
    async def auth_middleware(request, call_next):
        auth_error = verify_api_key(request)
        if auth_error:
            from starlette.responses import JSONResponse as StarletteJSONResponse
            return StarletteJSONResponse(content=auth_error, status_code=401)
        return await call_next(request)

    @mutate_api.post("/")
    def handle_mutate(payload: dict[str, Any]) -> dict[str, Any]:
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

            elif action == "load_agents":
                config = load_agents_config(commit_callback=data_volume.commit)
                return {"ok": True, "config": config}

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
                mime_type = payload.get("mime_type", "image/png")
                if not image_id or not image_base64:
                    return {"ok": False, "error": "Missing image_id or image_base64."}
                if "," in image_base64:
                    header, base64_data = image_base64.split(",", 1)
                    if "data:" in header and ";base64" in header:
                        mime_type = header.split("data:", 1)[1].split(";base64", 1)[0]
                else:
                    base64_data = image_base64
                img_bytes = base64.b64decode(base64_data)

                IMAGE_DIR.mkdir(parents=True, exist_ok=True)
                is_video = mime_type.startswith("video/") or mime_type == "video/mp4" or "video" in mime_type.lower()

                if is_video:
                    mp4_path = IMAGE_DIR / f"{image_id}.mp4"
                    with open(mp4_path, "wb") as f:
                        f.write(img_bytes)
                    webp_path = IMAGE_DIR / f"{image_id}.webp"
                    if webp_path.exists():
                        try:
                            webp_path.unlink()
                        except Exception:
                            pass
                    width = payload.get("width", 854)
                    height = payload.get("height", 480)
                    file_size = mp4_path.stat().st_size
                else:
                    webp_path = IMAGE_DIR / f"{image_id}.webp"
                    mp4_path = IMAGE_DIR / f"{image_id}.mp4"
                    if mp4_path.exists():
                        try:
                            mp4_path.unlink()
                        except Exception:
                            pass
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
                    file_size = webp_path.stat().st_size

                try:
                    web_url = get_image.get_web_url()
                except Exception:
                    web_url = "https://heebok-lee--areopagus-get-image.modal.run"

                web_url = web_url.rstrip("/")

                import time
                suffix = "&format=mp4" if is_video else ""
                new_url = f"{web_url}/?id={image_id}&v={int(time.time())}{suffix}"

                history = load_history()
                updated_any = False
                for turn in history.get("turns", []):
                    if turn.get("image_id") == image_id:
                        turn["image_url"] = new_url
                        if is_video:
                            turn["image_webp"] = {
                                "path": f"/data/images/{image_id}.mp4",
                                "url": new_url,
                                "format": "mp4",
                                "source_mime_type": mime_type,
                                "size_bytes": file_size,
                                "dimensions": {"width": width, "height": height},
                            }
                        else:
                            turn["image_webp"] = {
                                "path": f"/data/images/{image_id}.webp",
                                "url": new_url,
                                "format": "webp",
                                "quality": WEBP_QUALITY,
                                "source_mime_type": mime_type,
                                "size_bytes": file_size,
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
                            kw_cleaned = re.sub(r"[^a-z0-9#-]", "", kw_cleaned.replace(" ", ""))
                            if kw_cleaned not in {"#inspiration", "#design", "#photo", "#art", "#aesthetic", "#"}:
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

            elif action == "upload_brain_item":
                brain_id = payload.get("brain_id")
                item_type = payload.get("type", "image")
                source_file = payload.get("source_file", "")
                keywords = payload.get("keywords", [])
                summary = payload.get("summary", "")
                mood = payload.get("mood", "")
                title = payload.get("title", source_file)
                color_palette = payload.get("color_palette", [])
                excerpt = payload.get("excerpt", "")
                full_text = payload.get("full_text")
                image_base64 = payload.get("image_base64")

                if not brain_id:
                    return {"ok": False, "error": "Missing brain_id."}

                image_url = ""

                if image_base64 and item_type == "image":
                    if "," in image_base64:
                        header, base64_data = image_base64.split(",", 1)
                    else:
                        base64_data = image_base64
                    img_bytes = base64.b64decode(base64_data)

                    IMAGE_DIR.mkdir(parents=True, exist_ok=True)
                    webp_path = IMAGE_DIR / f"{brain_id}.webp"
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
                    image_url = f"{web_url}/?id={brain_id}"

                cleaned_keywords = []
                for kw in keywords:
                    if not isinstance(kw, str):
                        continue
                    kw_cleaned = kw.strip().lower()
                    if not kw_cleaned.startswith("#"):
                        kw_cleaned = "#" + kw_cleaned
                    kw_cleaned = re.sub(r"[^a-z0-9#-]", "", kw_cleaned.replace(" ", ""))
                    if kw_cleaned not in {"#inspiration", "#design", "#photo", "#art", "#aesthetic", "#"}:
                        cleaned_keywords.append(kw_cleaned)

                history = load_history()
                if "brain" not in history:
                    history["brain"] = []

                existing_item = None
                for item in history["brain"]:
                    if item.get("id") == brain_id:
                        existing_item = item
                        break

                brain_item = {
                    "id": brain_id,
                    "type": item_type,
                    "source_file": source_file,
                    "title": title,
                    "keywords": cleaned_keywords,
                    "summary": summary,
                    "mood": mood,
                    "color_palette": color_palette if isinstance(color_palette, list) else [],
                    "excerpt": excerpt,
                    "image_url": image_url,
                    "created_at": existing_item.get("created_at", utc_now()) if existing_item else utc_now(),
                    "updated_at": utc_now(),
                }

                if full_text and item_type in ("note", "document"):
                    brain_item["full_text"] = full_text

                if existing_item:
                    idx = history["brain"].index(existing_item)
                    history["brain"][idx] = brain_item
                else:
                    history["brain"].append(brain_item)

                brain_node_id = brain_id
                graph = history.setdefault("graph", {"nodes": [], "edges": []})
                existing_node_ids = {n["id"] for n in graph.get("nodes", []) if isinstance(n, dict)}

                if brain_node_id not in existing_node_ids:
                    graph["nodes"].append({
                        "id": brain_node_id,
                        "type": "brain" if item_type == "image" else f"brain-{item_type}",
                        "label": title or "Brain Item",
                        "url": image_url,
                    })

                for keyword in cleaned_keywords:
                    keyword_node_id = f"keyword-{keyword.lower().lstrip('#')}"
                    if keyword_node_id not in existing_node_ids and keyword_node_id not in {n["id"] for n in graph["nodes"]}:
                        graph["nodes"].append({
                            "id": keyword_node_id,
                            "type": "keyword",
                            "label": keyword,
                        })
                    graph["edges"].append({
                        "from": brain_node_id,
                        "to": keyword_node_id,
                        "relation": "tagged_with",
                    })

                save_history(history)
                return {"ok": True, "brain_item": brain_item}

            elif action == "delete_brain_item":
                brain_id = payload.get("id")
                if not brain_id:
                    return {"ok": False, "error": "Missing id."}
                history = load_history()
                brain_items = history.get("brain", [])
                target = None
                for item in brain_items:
                    if item.get("id") == brain_id:
                        target = item
                        break
                if not target:
                    return {"ok": False, "error": f"Brain item {brain_id} not found."}
                brain_items.remove(target)
                history["brain"] = brain_items
                try:
                    webp_path = IMAGE_DIR / f"{brain_id}.webp"
                    if webp_path.exists():
                        webp_path.unlink()
                except Exception as exc:
                    print(f"[delete_brain_item] Warning: failed to delete file: {exc}", flush=True)
                rebuild_history_graph(history)
                save_history(history)
                return {"ok": True, "message": f"Brain item {brain_id} deleted successfully."}

            elif action == "upload_brief":
                brief_id = payload.get("brief_id")
                title = payload.get("title", "")
                thesis = payload.get("thesis", "")
                visual_rules = payload.get("visual_rules", [])
                mood = payload.get("mood", "")
                color_palette = payload.get("color_palette", [])
                source_items = payload.get("source_items", [])
                keywords = payload.get("keywords", [])

                if not brief_id:
                    return {"ok": False, "error": "Missing brief_id."}

                cleaned_keywords = []
                for kw in keywords:
                    if not isinstance(kw, str):
                        continue
                    kw_cleaned = kw.strip().lower()
                    if not kw_cleaned.startswith("#"):
                        kw_cleaned = "#" + kw_cleaned
                    kw_cleaned = re.sub(r"[^a-z0-9#-]", "", kw_cleaned.replace(" ", ""))
                    if kw_cleaned not in {"#inspiration", "#design", "#photo", "#art", "#aesthetic", "#"}:
                        cleaned_keywords.append(kw_cleaned)

                history = load_history()
                if "briefs" not in history:
                    history["briefs"] = []

                existing_brief = None
                for brief in history["briefs"]:
                    if brief.get("brief_id") == brief_id:
                        existing_brief = brief
                        break

                brief_item = {
                    "brief_id": brief_id,
                    "title": title,
                    "thesis": thesis,
                    "visual_rules": visual_rules if isinstance(visual_rules, list) else [],
                    "mood": mood,
                    "color_palette": color_palette if isinstance(color_palette, list) else [],
                    "source_items": source_items if isinstance(source_items, list) else [],
                    "keywords": cleaned_keywords,
                    "active": True,
                    "auto_generated": True,
                    "created_at": existing_brief.get("created_at", utc_now()) if existing_brief else utc_now(),
                    "updated_at": utc_now(),
                }

                if existing_brief:
                    idx = history["briefs"].index(existing_brief)
                    history["briefs"][idx] = brief_item
                else:
                    history["briefs"].append(brief_item)

                graph = history.setdefault("graph", {"nodes": [], "edges": []})
                existing_node_ids = {n["id"] for n in graph.get("nodes", []) if isinstance(n, dict)}

                if brief_id not in existing_node_ids:
                    graph["nodes"].append({
                        "id": brief_id,
                        "type": "brief",
                        "label": title or "Creative Brief",
                    })

                for keyword in cleaned_keywords:
                    keyword_node_id = f"keyword-{keyword.lower().lstrip('#')}"
                    if keyword_node_id not in existing_node_ids and keyword_node_id not in {n["id"] for n in graph["nodes"]}:
                        graph["nodes"].append({
                            "id": keyword_node_id,
                            "type": "keyword",
                            "label": keyword,
                        })
                    graph["edges"].append({
                        "from": brief_id,
                        "to": keyword_node_id,
                        "relation": "tagged_with",
                    })

                for source_id in source_items:
                    if source_id in existing_node_ids or source_id in {n["id"] for n in graph["nodes"]}:
                        graph["edges"].append({
                            "from": brief_id,
                            "to": source_id,
                            "relation": "synthesized_from",
                        })

                save_history(history)
                return {"ok": True, "brief": brief_item}

            elif action == "delete_brief":
                brief_id = payload.get("brief_id")
                if not brief_id:
                    return {"ok": False, "error": "Missing brief_id."}
                history = load_history()
                briefs = history.get("briefs", [])
                target = None
                for brief in briefs:
                    if brief.get("brief_id") == brief_id:
                        target = brief
                        break
                if not target:
                    return {"ok": False, "error": f"Brief {brief_id} not found."}
                briefs.remove(target)
                history["briefs"] = briefs
                rebuild_history_graph(history)
                save_history(history)
                return {"ok": True, "message": f"Brief {brief_id} deleted successfully."}

            elif action == "simplify_keywords":
                history = load_history()

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

                def map_keywords(kws):
                    new_kws = []
                    for kw in kws:
                        mapped = mapping.get(kw)
                        if isinstance(mapped, list):
                            for m in mapped:
                                m_cleaned = m.strip().lower()
                                if not m_cleaned.startswith("#"):
                                    m_cleaned = "#" + m_cleaned
                                m_cleaned = re.sub(r"[^a-z0-9#-]", "", m_cleaned.replace(" ", ""))
                                if m_cleaned not in {"#inspiration", "#design", "#photo", "#art", "#aesthetic", "#"} and m_cleaned not in new_kws:
                                    new_kws.append(m_cleaned)
                        else:
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

    return mutate_api


@app.function(
    image=image,
    volumes={"/data": data_volume},
    secrets=[modal.Secret.from_dotenv()],
    timeout=60,
)
@modal.fastapi_endpoint(method="POST")
def pulse_endpoint(request: Request, payload: dict[str, Any]) -> dict[str, Any]:
    auth_error = verify_api_key(request)
    if auth_error:
        return auth_error
    AGENTS_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with AGENTS_CONFIG_PATH.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    data_volume.commit()
    
    # Run orchestrate asynchronously so the request doesn't block
    orchestrate.spawn(payload)
    
    return {"ok": True, "message": "Pulse started remotely on Modal."}


# ── Heartbeat Cron ────────────────────────────────────────────────────────────

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

    agents_config = load_agents_config(commit_callback=data_volume.commit)
    freq = max_heartbeat_frequency(agents_config)

    if freq <= 0:
        print("[heartbeat_cron] No active agents with heartbeat > 0. Skipping.", flush=True)
        return

    interval = heartbeat_interval_seconds(freq)
    state = read_heartbeat_state()
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
    write_heartbeat_state({
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


@app.function(image=image, volumes={"/data": data_volume})
def generate_missing_thumbnails():
    import subprocess
    from pathlib import Path
    
    images_dir = Path("/data/images")
    if not images_dir.exists():
        print("No images dir found.")
        return
        
    for mp4_path in images_dir.glob("*.mp4"):
        webp_path = mp4_path.with_suffix(".webp")
        if not webp_path.exists():
            print(f"Extracting first frame from {mp4_path} to {webp_path}")
            try:
                subprocess.run([
                    "ffmpeg", "-y", "-i", str(mp4_path),
                    "-vframes", "1", "-f", "image2", str(webp_path)
                ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
                print(f"Success: {webp_path.name}")
            except Exception as e:
                print(f"Failed to extract for {mp4_path.name}: {e}")
                
    data_volume.commit()
