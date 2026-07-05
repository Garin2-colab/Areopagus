from __future__ import annotations
from typing import TypedDict, NotRequired, Any

class HistoryTurn(TypedDict):
    turn: int
    image_id: str | None
    image_url: str | None
    prompt_text: str
    keywords: list[str]
    agent_id: str
    action: str  # 'initiate', 'pivot', 'comment'
    thread_id: str
    category: str | None
    parent_turn: int | None
    timestamp: str

class BrainItem(TypedDict):
    id: str
    type: str  # 'image' | 'note' | 'reference'
    title: str
    keywords: list[str]
    summary: str
    mood: str
    color_palette: list[str]
    image_url: str | None
    source_file: str
    full_text: NotRequired[str | None]
    timestamp: str

class BriefItem(TypedDict):
    brief_id: str
    title: str
    thesis: str
    visual_rules: list[str]
    mood: str
    color_palette: list[str]
    source_items: list[str]
    keywords: list[str]
    active: bool
    auto_generated: bool
    timestamp: str

class InspirationItem(TypedDict):
    id: str
    image_url: str
    keywords: list[str]

class GraphNode(TypedDict):
    id: str
    label: str
    type: str  # 'agent' | 'keyword' | 'category' | 'brain_item' | 'brief' | 'turn'
    val: NotRequired[int]

class GraphEdge(TypedDict):
    source: str
    target: str
    type: str  # 'created_by' | 'tagged_with' | 'synthesized_from' | 'replied_to' | 'references'

class GraphData(TypedDict):
    nodes: list[GraphNode]
    edges: list[GraphEdge]

class HistoryData(TypedDict):
    project: NotRequired[str]
    created_at: NotRequired[str]
    updated_at: NotRequired[str]
    turns: list[HistoryTurn]
    threads: list[dict[str, Any]]
    inspiration: NotRequired[list[InspirationItem]]
    brain: NotRequired[list[BrainItem]]
    briefs: NotRequired[list[BriefItem]]
    graph: GraphData

class AgentConfig(TypedDict):
    id: str
    name: str
    persona: str
    model: str
    heartbeatMinutes: int
    referenceImages: list[str]
    active: bool

class AgentConfigsPayload(TypedDict):
    agents: list[AgentConfig]
    updated_at: NotRequired[str]

