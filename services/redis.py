import json
import redis.asyncio as redis
from sqlalchemy import select
from core.config import HISTORY_SUMMARY_MEMORY_TTL, REDIS_URL, EPISODIC_TTL
from db.database import AsyncSessionLocal
from db.models import EpisodicMemory, UserMemorySetting
import asyncio
import logging
logger = logging.getLogger(__name__)

pool = redis.from_url(REDIS_URL, decode_responses=True)


# ____________________ token ___________________________

async def save_reset_token(user_id: int, token: str, ttl_sec: int = 600) -> None:
    await pool.setex(f"pwd_reset:{token}", ttl_sec, str(user_id))

async def get_reset_user(token: str) -> int | None:
    uid = await pool.get(f"pwd_reset:{token}")
    return int(uid) if uid else None

async def delete_token(token: str) -> None:
    await pool.delete(f"pwd_reset:{token}")


# ____________________ episodic memory ___________________________

async def user_allows_episodic(user_id: int) -> bool:
    async with AsyncSessionLocal() as db:
        row = await db.scalar(select(UserMemorySetting).filter_by(user_id=user_id))
        return row.allow_episodic if row else True

async def push_episodic_turn(user_id: int, thread_id: str, role: str, content: str):

    if await user_allows_episodic(user_id):
        key = f"episodic:{user_id}:{thread_id}"
        payload = json.dumps({"role": role, "content": content})
        await pool.lpush(key, payload)
        await pool.ltrim(key, 0, 19)          # keep last 20 turns
        await pool.expire(key, EPISODIC_TTL)

        # cold path – MySQL (fire-and-forget)
        asyncio.create_task(_persist_episode(user_id, thread_id, role, content))
    else:
        logger.info("User %s disallowed episodic saves", user_id)
        return {"ok": False, "reason": "user_disabled"}

async def get_episodic_turns(user_id: int, thread_id: str) -> list[dict]:
    key = f"episodic:{user_id}:{thread_id}"
    items = await pool.lrange(key, 0, -1)
    return [json.loads(i) for i in reversed(items)]   # oldest→newest


async def _persist_episode(user_id: int, thread_id: str, role: str, content: str):
    """Async insert without blocking chat."""
    try:
        async with AsyncSessionLocal() as db:
            db.add(EpisodicMemory(user_id=user_id, thread_id=thread_id, role=role, content=content))
            await db.commit()
    except Exception:
        # log but never crash the chat
        pass



# ____________________ All messages history summarization memory ___________________________

async def get_summary(user_id: int, thread_id: str) -> str | None:
    key = f"summary:{user_id}:{thread_id}"
    raw = await pool.get(key)
    return raw.decode() if raw else None

async def set_summary(user_id: int, thread_id: str, summary: str):
    key = f"summary:{user_id}:{thread_id}"
    await pool.setex(key, HISTORY_SUMMARY_MEMORY_TTL, summary)
    logger.info("User summary setted", user_id)