from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from db.models import User, UserTool, Tool
from core.database import get_db
from api.dependencies import get_current_user
from api.schemas.user_tool_view import UserToolView



router = APIRouter(prefix="/user_tool", tags=["User Tool View"])


@router.post("/view", response_model=UserToolView)
async def user_tool_view(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    view according to particular user
    """

    stmt = (
        select(
            Tool.id,
            Tool.name,
            Tool.description,
            Tool.status,
            UserTool.status.label("user_tool_status"),
        )
        .join(UserTool, UserTool.tool_id == Tool.id)
        .where((UserTool.user_id == user.id))
    )

    rows = (await db.execute(stmt)).all()
    await db.commit()
    
    tools = [
        {
            "id": r.id,
            "name": r.name,
            "description": r.description,
            "status": r.status,          # global status (active/inactive)
            "user_tool_status": r.user_tool_status,  # allowed/denied
        }
        for r in rows
    ]

    return {"tools": tools}