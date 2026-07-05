from core.history import is_agent_allowed_to_reply

# Mock history case 1: Agent 1 initiated, no replies or comments from other agents.
history_1 = {
    "turns": [
        {"thread_id": "thread-A", "action": "Initiate", "agent_id": "agent-1", "turn": 1}
    ],
    "threads": [
        {"thread_id": "thread-A", "agent_id": "agent-1", "posts": ["image-A"], "comments": []}
    ]
}

# Mock history case 2: Agent 1 initiated, comment from Agent 2 exists.
history_2 = {
    "turns": [
        {"thread_id": "thread-A", "action": "Initiate", "agent_id": "agent-1", "turn": 1}
    ],
    "threads": [
        {
            "thread_id": "thread-A",
            "agent_id": "agent-1",
            "posts": ["image-A"],
            "comments": [
                {"agent_id": "agent-2", "comment": "Nice work!"}
            ]
        }
    ]
}

# Mock history case 3: Agent 1 initiated, another turn from Agent 2 in turns.
history_3 = {
    "turns": [
        {"thread_id": "thread-A", "action": "Initiate", "agent_id": "agent-1", "turn": 1},
        {"thread_id": "thread-A", "action": "Critique", "agent_id": "agent-2", "turn": 2}
    ],
    "threads": [
        {"thread_id": "thread-A", "agent_id": "agent-1", "posts": ["image-A", "image-B"], "comments": []}
    ]
}

print("Case 1 (Initiator agent-1, no comments/replies):")
print("  agent-1 allowed:", is_agent_allowed_to_reply("agent-1", "thread-A", history_1))
print("  agent-2 allowed:", is_agent_allowed_to_reply("agent-2", "thread-A", history_1))

print("Case 2 (Initiator agent-1, comments from agent-2):")
print("  agent-1 allowed:", is_agent_allowed_to_reply("agent-1", "thread-A", history_2))

print("Case 3 (Initiator agent-1, turn from agent-2):")
print("  agent-1 allowed:", is_agent_allowed_to_reply("agent-1", "thread-A", history_3))
