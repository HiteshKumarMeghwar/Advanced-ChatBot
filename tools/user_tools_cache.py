CACHE_TTL = 60  # seconds

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from core.database import get_db
from fastapi import Depends
from db.models import Tool, UserTool
from services.redis import pool


async def get_user_allowed_tool_names(
    user_id: int,
    db: AsyncSession = Depends(get_db),
):
    key = f"user:{user_id}:tools"

    cached = await pool.get(key)
    if cached:
        return set(cached.split(","))

    stmt = (
        select(Tool.name)
        .join(UserTool, UserTool.tool_id == Tool.id)
        .where(
            Tool.status == "active",
            UserTool.user_id == user_id,
            UserTool.status == "allowed",
        )
    )
    result = await db.execute(stmt)
    names = {row[0] for row in result.fetchall()}

    await pool.set(key, ",".join(names), ex=CACHE_TTL)
    return names
