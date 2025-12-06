# services/redis.py
import redis.asyncio as redis
from core.config import REDIS_URL

pool = redis.from_url(REDIS_URL, decode_responses=True)

async def save_reset_token(user_id: int, token: str, ttl_sec: int = 600) -> None:
    await pool.setex(f"pwd_reset:{token}", ttl_sec, str(user_id))

async def get_reset_user(token: str) -> int | None:
    uid = await pool.get(f"pwd_reset:{token}")
    return int(uid) if uid else None

async def delete_token(token: str) -> None:
    await pool.delete(f"pwd_reset:{token}")