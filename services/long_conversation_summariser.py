import asyncio
from langchain_core.messages import SystemMessage
from core.config import LLM_TIMEOUT
from graphs.bind_tool_with_llm import groq_without_tool_llm
from services.redis import get_summary, set_summary
import logging

logger = logging.getLogger(__name__)


DELTA_PROMPT = SystemMessage(
    content="You already have a summary of the conversation so far:\n\n{existing_summary}\n\n"
    "Below are the NEW messages that happened after that summary.\n"
    "Produce a **short bullet list** (1-3 items) that captures **only the new facts, preferences, or unfinished business** "
    "and append them to the existing summary. Keep the whole thing under 200 tokens.\n\n"
    "NEW MESSAGES:\n{new_messages}"
)

SUMMARY_PROMPT = SystemMessage(
    content="Below is an entire conversation. "
    "Produce a concise, chronological summary (3-5 bullet points) that captures "
    "key facts, preferences, and unfinished business. "
    "Keep it under 200 tokens.\n\nConversation:\n{conversation}"
)

async def summarise_history(user_id: int, thread_id: str, messages: list, llms) -> str:
    cached = await get_summary(user_id, thread_id)
    if cached:
        return cached

    llm = llms["system"]
    conversation = "\n".join(f"{m.type}: {m.content}" for m in messages)
    try:
        resp = await asyncio.wait_for(llm.ainvoke([SUMMARY_PROMPT.format(conversation=conversation)]), timeout=LLM_TIMEOUT)
        summary = resp.content.strip()
    except Exception as e:
        logger.warning("Summary failed: %s", e)
        summary = ""

    if summary:
        await set_summary(user_id, thread_id, summary)
    return summary



async def summarise_history_incremental(
    user_id: int, 
    thread_id: str, 
    all_messages: list,
    config
) -> str:
    """
    Incremental summary:
    1.  If no cache → full summary (cheap fallback)
    2.  If cache exists → summarise only messages AFTER the last cached turn
    3.  Append delta to existing summary and store back
    """
    llms = config.get("configurable", {}).get("llms")
    cached = await get_summary(user_id, thread_id)
    if not cached:
        # first time → full summary (fallback)
        return await _full_summary(user_id, thread_id, all_messages, llms)

    # find first message that is NOT in the cached summary (heuristic: length)
    #   - we store the message count inside the cached blob for accuracy
    try:
        lines = cached.splitlines()
        msg_count = int(lines[0].split("::")[1])  # first line:  "::123"
        new_msgs = all_messages[msg_count:]
    except (IndexError, ValueError):
        # fallback – resummarise everything
        return await _full_summary(user_id, thread_id, all_messages, llms)

    if not new_msgs:
        return cached  # nothing new

    llm = llms["system"]
    delta_text = "\n".join(f"{m.type}: {m.content}" for m in new_msgs)
    try:
        resp = await asyncio.wait_for(llm.ainvoke(
            [
                DELTA_PROMPT.format(
                    existing_summary="\n".join(lines[1:]),  # skip header
                    new_messages=delta_text,
                )
            ]),
            timeout=LLM_TIMEOUT,
        )
        updated = f"::{len(all_messages)}\n" + resp.content.strip()
    except Exception as e:
        logger.warning("Incremental summary failed: %s", e)
        return cached  # graceful degrade

    await set_summary(user_id, thread_id, updated)
    return updated


# ---------- private ----------
async def _full_summary(user_id: int, thread_id: str, messages: list, llms) -> str:
    """Old brute-force summary - kept for cold start."""
    
    full = await summarise_history(user_id, thread_id, messages, llms)
    # prepend message count so we know where to resume
    return f"::{len(messages)}\n{full}"
