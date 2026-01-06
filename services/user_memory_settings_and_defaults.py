from sqlalchemy import select
from core.config import USER_MEMORY_DEFAULTS
from db.database import AsyncSessionLocal
from db.models import UserMemorySetting


async def get_user_memory_settings_or_default(user_id: int):
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