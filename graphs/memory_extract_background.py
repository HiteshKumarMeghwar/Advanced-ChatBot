import asyncio
import time
from graphs.memory_extract import extract_memory
from graphs.state import ChatState
import logging
logger = logging.getLogger(__name__)


async def extract_memory_background(state: ChatState, config=None):
    t0 = time.perf_counter()
    trace = config.get("configurable", {}).get("trace")

    async def _background():
        try:
            await extract_memory(state, config)
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
