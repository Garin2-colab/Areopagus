from typing import Any
from core.utils import utc_now

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

    # Process brain items (Second Brain)
    for item in history.get("brain", []):
        if not isinstance(item, dict) or "id" not in item:
            continue

        brain_id = item["id"]
        item_type = item.get("type", "image")
        node_type = "brain" if item_type == "image" else f"brain-{item_type}"

        if brain_id not in {n["id"] for n in history["graph"]["nodes"]}:
            history["graph"]["nodes"].append({
                "id": brain_id,
                "type": node_type,
                "label": item.get("title", "Brain Item"),
                "url": item.get("image_url", ""),
            })

        for keyword in item.get("keywords", []):
            if not keyword:
                continue
            keyword_node_id = f"keyword-{keyword.lower().lstrip('#')}"

            if keyword_node_id not in {n["id"] for n in history["graph"]["nodes"]}:
                history["graph"]["nodes"].append({
                    "id": keyword_node_id,
                    "type": "keyword",
                    "label": keyword,
                })

            history["graph"]["edges"].append({
                "from": brain_id,
                "to": keyword_node_id,
                "relation": "tagged_with",
            })
