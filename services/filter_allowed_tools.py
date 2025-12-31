from typing import List
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from db.models import User, Tool, UserTool


async def filter_allowed_tools(
    gathered_tools: List,
    db: AsyncSession,
    user: User,
) -> List:
    """
    Enforces enterprise tool governance.
    """

    if not gathered_tools:
        return []

    gathered_map = {
        tool.name: tool
        for tool in gathered_tools
        if hasattr(tool, "name")
    }

    if not gathered_map:
        return []

    stmt = (
        select(Tool.name)
        .join(UserTool, UserTool.tool_id == Tool.id)
        .where(
            Tool.name.in_(gathered_map.keys()),
            Tool.status == "active",
            UserTool.user_id == user.id,
            UserTool.status == "allowed",
        )
    )

    result = await db.execute(stmt)
    allowed = {row[0] for row in result.fetchall()}

    return [gathered_map[name] for name in allowed]
