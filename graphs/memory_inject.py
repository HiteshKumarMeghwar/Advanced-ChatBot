# graphs/memory_inject.py

import time
from sqlalchemy import select
from core.config import HISTORY_SUMMARY_MEMORY_LIMIT, USER_MEMORY_DEFAULTS
from services.long_conversation_summariser import summarise_history_incremental
from services.redis import get_episodic_turns
from services.semantic_memory import query_semantic_facts
from services.procedural_memory import get_rules #, user_allows_procedural  # implement user check if needed
from graphs.state import ChatState
from db.database import AsyncSessionLocal
from db.models import UserMemorySetting

async def get_user_settings_or_default(user_id: int):
    async with AsyncSessionLocal() as db:
        row = await db.scalar(select(UserMemorySetting).filter_by(user_id=user_id))
        if not row:
            return USER_MEMORY_DEFAULTS
        return {
            "allow_episodic": row.allow_episodic,
            "allow_semantic": row.allow_semantic,
            "allow_procedural": row.allow_procedural,
            "allow_long_conversation_memory": row.allow_long_conversation_memory,
            "semantic_retention_days": row.semantic_retention_days,
        }

async def inject_memory(state: ChatState, config=None):
    t0 = time.perf_counter()
    user_id = state["user_id"]
    thread_id = state["thread_id"]
    total = len(state["messages"])
    settings = await get_user_settings_or_default(user_id)
    trace = config.get("configurable", {}).get("trace")

    if settings["allow_episodic"]:
        state["episodic_memories"] = await get_episodic_turns(user_id, thread_id)
    else:
        state["episodic_memories"] = []

    if settings["allow_semantic"]:
        last_user_msg = next(
            (m.content for m in reversed(state["messages"]) if m.type == "human"), ""
        )
        state["semantic_memories"] = await query_semantic_facts(user_id, last_user_msg)
    else:
        state["semantic_memories"] = []

    if settings["allow_procedural"]:
        state["procedural_memories"] = await get_rules(user_id)
    else:
        state["procedural_memories"] = []

    if settings["allow_long_conversation_memory"]:
        if total > HISTORY_SUMMARY_MEMORY_LIMIT:
            state["long_history_memories"] = await summarise_history_incremental(
                state["user_id"], state["thread_id"], state["messages"][:-5], config
            )
        else:
            state["long_history_memories"] = []

    trace["events"].append({
        "node": "inject_memory",
        "latency_ms": (time.perf_counter() - t0) * 1000,
    })

    return state
