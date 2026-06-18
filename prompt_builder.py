from typing import Any, Dict, List
import json


def retrieve_matching_briefs(
    history: dict[str, Any] | None,
    current_keywords: list[str],
    max_briefs: int = 2,
) -> list[dict[str, Any]]:
    """
    Layer 2→3 bridge: Find Creative Briefs whose keywords overlap
    with the current context. Returns the top matching active briefs.
    """
    if not history:
        return []
    briefs = history.get("briefs", [])
    if not briefs:
        return []

    current_set = {k.lower() for k in current_keywords}
    scored: list[tuple[int, dict[str, Any]]] = []

    for brief in briefs:
        if not brief.get("active", True):
            continue
        brief_keywords = {k.lower() for k in brief.get("keywords", [])}
        overlap = brief_keywords.intersection(current_set)
        if len(overlap) >= 2:
            scored.append((len(overlap), brief))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [brief for _, brief in scored[:max_briefs]]

def build_futurist_prompt(
    schema_template: dict[str, Any],
    turn_index: int,
    previous_turns: list[dict[str, Any]],
) -> dict[str, Any]:
    from orchestrator import gemini_generate, sanitize_for_runway, prompt_theme, dedupe_keywords
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
            f"Agent 1 proposes Turn {turn_index} with a focus on {prompt_theme(turn_index)}."
        )
    if "keywords" not in prompt_json or not isinstance(prompt_json["keywords"], list):
        prompt_json["keywords"] = ["#areopagus", "#futurist", f"#{prompt_theme(turn_index).replace(' ', '')}"]
    prompt_json["keywords"] = dedupe_keywords(prompt_json["keywords"])
    return prompt_json


def build_initiate_prompt_json(
    agent: dict[str, Any],
    recent_turns: list[dict[str, Any]],
    assessment: dict[str, Any],
    schema_template: dict[str, Any],
    turn_number: int,
    history: dict[str, Any] | None = None,
) -> dict[str, Any]:
    from models import get_model
    from orchestrator import (
        fetch_image_bytes,
        retrieve_associative_memory,
        agent_style_slots,
        agent_gemini_model,
        gemini_generate,
        sanitize_for_runway,
        summarize_turn_for_agent,
        dedupe_keywords,
    )
    raw_model = agent.get("selected_model") or agent.get("model") or "gpt_image_2"
    model_handler = get_model(raw_model)

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
    guidance = model_handler.get_prompt_guidance_text(bool(prompt_img_url))
    if guidance:
        prompt += guidance

    if inspiration_image_id and inspiration_meta:
        prompt += f"""
NOTE: An associative memory from the Knowledge Web has been recalled:
- Inspiration Turn: Turn {inspiration_meta.get('turn')}
- Inspiration Image ID: {inspiration_image_id}
- Inspiration Keywords: {inspiration_meta.get('keywords')}
- Inspiration Proposal: "{inspiration_meta.get('proposal')}"

This image is attached to your visual context with the tag '@InspirationRef'. If you choose to blend its concepts, styles, or compositions, you must reference '@InspirationRef' in your style or description fields, and you must set `"inspiration_image_id": "{inspiration_image_id}"` in the returned JSON. If you do not choose to reference it, set `"inspiration_image_id": null`.
"""

    # Layer 2→3: Inject matching Creative Briefs
    if history:
        all_keywords = []
        for turn in recent_turns:
            all_keywords.extend(turn.get("keywords", []))
        matching_briefs = retrieve_matching_briefs(history, all_keywords)
        if matching_briefs:
            for bi, brief in enumerate(matching_briefs, 1):
                rules_str = "\n".join(f"  - {r}" for r in brief.get("visual_rules", []))
                prompt += f"""
📋 ACTIVE CREATIVE BRIEF {bi}: "{brief.get('title', 'Untitled')}"
Thesis: {brief.get('thesis', '')}
Visual Rules:
{rules_str}
Mood: {brief.get('mood', '')}

You SHOULD incorporate these directives into your composition when they align with your persona.
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
- `scene_description` should be highly diverse in structure and length. It can be a simple direct sentence, an abstract/surreal conceptual description, or a complex hyper-detailed visual shoot script (1 to 5 sentences) blending subject, attire, lighting, environment, style, and camera. Do not follow a rigid template.
- Add turn, debate_context, proposal, keywords, reference_image_id, and inspiration_image_id.
- proposal should be 2 to 3 sentences and should explain the design move the agent is initiating.
- keywords must be exactly 5 simple, intuitive, hash-tagged strings. Avoid complex, composite/merged words like '#impossiblegeometryflux' or '#monochromeminimalism'. Instead, split them into separate simple concepts (e.g. '#impossiblegeometry', '#flux'; '#monochrome', '#minimalism'). NEVER use generic words like '#inspiration', '#design', '#image', '#photo', '#art', or '#aesthetic'.
- For `aspect_ratio`, dynamically select the most appropriate aspect ratio for the visual composition you are designing. Choose strictly from the following allowed ratios: ["1:1", "16:9", "9:16", "4:3", "3:4", "21:9", "2:3", "3:2", "4:5", "5:4"]. For example, use "16:9" or "21:9" for expansive horizontal landscapes, "9:16" or "3:4" for vertical/portrait/human figures, and "1:1" for focused central/abstract compositions.
- reference_image_id: You must decide whether to use a style/composition reference image for this generation or generate completely from scratch.
  - If you want to use your baseline style image as a reference, set reference_image_id to "profile".
  - If you want to use one of your general reference style images from the profile, set reference_image_id to the slot name (e.g. "AgentRef1", "AgentRef2", etc.) if present in your style_slots.
  - If you want to generate completely from scratch without image references, set reference_image_id to null.
"""
    rules_text = model_handler.get_prompt_rules_text(bool(prompt_img_url), action="Initiate")
    if rules_text:
        prompt += rules_text

    prompt += f"""
- inspiration_image_id: Set this to the string ID of the inspiration image (e.g., "{inspiration_image_id or ''}") if you referenced it, or null.
- The output should feel cinematic, architectural, ceremonial, and specific to the active agent persona.
"""
    suffix_text = model_handler.get_prompt_suffix_text(bool(prompt_img_url))
    if suffix_text:
        prompt += suffix_text

    prompt += "\n- Return JSON only.\n"

    prompt_json = gemini_generate(
        prompt,
        image_bytes=image_bytes,
        image_mime_type=image_mime_type,
        extra_images=extra_images if extra_images else None,
        model=agent_gemini_model(agent)
    )
    prompt_json = sanitize_for_runway(prompt_json)
    prompt_json = model_handler.post_process_prompt_json(prompt_json)
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


def build_pivot_prompt_json(
    agent: dict[str, Any],
    selected_turn: dict[str, Any],
    recent_turns: list[dict[str, Any]],
    assessment: dict[str, Any],
    schema_template: dict[str, Any],
    turn_number: int,
    history: dict[str, Any] | None = None,
) -> dict[str, Any]:
    from models import get_model
    from orchestrator import (
        fetch_image_bytes,
        retrieve_associative_memory,
        agent_style_slots,
        agent_gemini_model,
        gemini_generate,
        sanitize_for_runway,
        summarize_turn_for_agent,
        dedupe_keywords,
        prompt_payload_for_turn,
    )
    raw_model = agent.get("selected_model") or agent.get("model") or "gpt_image_2"
    model_handler = get_model(raw_model)

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

    # Layer 2→3: Inject matching Creative Briefs for pivot
    if history:
        pivot_keywords = list(selected_turn.get("keywords", []))
        for turn in recent_turns:
            pivot_keywords.extend(turn.get("keywords", []))
        matching_briefs = retrieve_matching_briefs(history, pivot_keywords)
        if matching_briefs:
            for bi, brief in enumerate(matching_briefs, 1):
                rules_str = "\n".join(f"  - {r}" for r in brief.get("visual_rules", []))
                prompt += f"""
📋 ACTIVE CREATIVE BRIEF {bi}: "{brief.get('title', 'Untitled')}"
Thesis: {brief.get('thesis', '')}
Visual Rules:
{rules_str}
Mood: {brief.get('mood', '')}

You SHOULD incorporate these directives into your composition when they align with your persona.
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
- `scene_description` should be highly diverse in structure and length. It can be a simple direct sentence, an abstract/surreal conceptual description, or a complex hyper-detailed visual shoot script (1 to 5 sentences) blending subject, attire, lighting, environment, style, and camera. Do not follow a rigid template.
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
"""
    rules_text = model_handler.get_prompt_rules_text(bool(selected_turn.get("image_url")), action="Pivot")
    if rules_text:
        prompt += rules_text

    prompt += f"""
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
    prompt_json = model_handler.post_process_prompt_json(prompt_json)
    prompt_json["debate_context"] = sanitize_for_runway([summarize_turn_for_agent(turn) for turn in recent_turns])
    if not isinstance(prompt_json.get("proposal"), str) or not prompt_json["proposal"].strip():
        prompt_json["proposal"] = (
            f"{agent.get('name', 'Agent')} pivots/refines the thread visual based on the previous frame. "
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
    from orchestrator import (
        agent_gemini_model,
        gemini_generate,
        summarize_turn_for_agent,
    )
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
