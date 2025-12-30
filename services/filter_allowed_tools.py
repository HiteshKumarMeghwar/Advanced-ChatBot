from typing import List
from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_current_user
from core.database import get_db
from db.models import User, Tool, UserTool


async def filter_allowed_tools(
    gathered_tools: List,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> List:
    """
    Enforces enterprise tool governance.

    Rules:
    - Tool must exist in `tools` table
    - Tool.status must be `active`
    - UserTool.status must be `allowed`

    Only approved tools are returned for LLM binding.
    """

    if not gathered_tools:
        return []

    # --- Build name → tool_object map from gathered tools ---
    gathered_map = {
        tool.name: tool
        for tool in gathered_tools
        if hasattr(tool, "name")
    }

    tool_names = list(gathered_map.keys())

    if not tool_names:
        return []

    # --- Query governance layer ---
    stmt = (
        select(Tool.name)
        .join(UserTool, UserTool.tool_id == Tool.id)
        .where(
            Tool.name.in_(tool_names),
            Tool.status == "active",
            UserTool.user_id == user.id,
            UserTool.status == "allowed",
        )
    )

    result = await db.execute(stmt)
    allowed_tool_names = {row[0] for row in result.fetchall()}

    # --- Return only policy-approved runtime tools ---
    return [
        gathered_map[name]
        for name in allowed_tool_names
        if name in gathered_map
    ]
