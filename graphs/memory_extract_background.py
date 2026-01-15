import asyncio
import time
from core.config import HISTORY_SUMMARY_MEMORY_LIMIT
from core.llm_limits import BACKGROUND_LLM_SEMAPHORE
from graphs.memory_extract import extract_memory
from graphs.state import ChatState
import logging
from services.long_conversation_summariser import summarise_history_incremental
from services.user_memory_settings_and_defaults import get_user_memory_settings_or_default
logger = logging.getLogger(__name__)


async def extract_memory_background(state: ChatState, config=None):
    messages_snapshot = state.get("__bg_messages__", [])
    t0 = time.perf_counter()
    trace = config.get("configurable", {}).get("trace")
    settings = await get_user_memory_settings_or_default(int(state["user_id"]))

    async def _background():
        async with BACKGROUND_LLM_SEMAPHORE:
            try:
                # --------- extraction (episodic,semantic,procedural) memory --------------------
                await extract_memory(
                    int(state["user_id"]),
                    state["thread_id"],
                    messages_snapshot,
                    config
                )

                # --------- summarization if >30 messages in current conversation --------------------
                if len(messages_snapshot) > HISTORY_SUMMARY_MEMORY_LIMIT and settings["allow_long_conversation_memory"]:
                    await summarise_history_incremental(
                        int(state["user_id"]),
                        state["thread_id"],
                        messages_snapshot[:-2],
                        config
                    )

            except Exception:
                logger.exception("Async memory extraction failed")

    asyncio.create_task(_background())

    trace["events"].append({
        "node": "extract_memory",
        "latency_ms": (time.perf_counter() - t0) * 1000,
    })
    total = (time.perf_counter() - trace["start_ts"]) * 1000
    logger.info(
        "Chat latency %.2fms | breakdown=%s",
        total,
        trace["events"],
    )
    return state
