# graphs/memory_inject.py
import time
from services.redis import get_episodic_turns, get_summary
from services.semantic_memory import query_semantic_facts
from services.procedural_memory import get_rules #, user_allows_procedural  # implement user check if needed
from graphs.state import ChatState
from services.user_memory_settings_and_defaults import get_user_memory_settings_or_default

async def inject_memory(state: ChatState, config=None):
    t0 = time.perf_counter()
    user_id = int(state["user_id"])
    thread_id = state["thread_id"]
    settings = await get_user_memory_settings_or_default(user_id)
    trace = config.get("configurable", {}).get("trace")

    if settings["allow_episodic"]:
        state["episodic_memories"] = await get_episodic_turns(user_id, thread_id) or []
    else:
        state["episodic_memories"] = []

    if settings["allow_semantic"]:
        last_user_msg = next(
            (m.content for m in reversed(state["messages"]) if m.type == "human"), ""
        )
        state["semantic_memories"] = await query_semantic_facts(user_id, last_user_msg) or []
    else:
        state["semantic_memories"] = []

    if settings["allow_procedural"]:
        state["procedural_memories"] = await get_rules(user_id) or []
    else:
        state["procedural_memories"] = []

    if settings["allow_long_conversation_memory"]:
        summary = await get_summary(user_id, thread_id)
        state["long_history_memories"] = summary if summary else ""
    else:
        state["long_history_memories"] = ""

    trace["events"].append({
        "node": "inject_memory",
        "latency_ms": (time.perf_counter() - t0) * 1000,
        "memory": {
            "episodic": len(state["episodic_memories"]),
            "semantic": len(state["semantic_memories"]),
            "procedural": len(state["procedural_memories"]),
            "summary": bool(state["long_history_memories"]),
        }
    })

    # 👇 UI-safe signal
    if any([
        state["episodic_memories"],
        state["semantic_memories"],
        state["procedural_memories"],
        state["long_history_memories"],
    ]):
        trace["ui_events"].append({
            "type": "memory_used",
            "severity": "info",
        })

    return state
