from fastapi import APIRouter, Depends
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession
from db.models import User, UserTool
from core.database import get_db
from api.schemas.user_tool_status import UserToolStatus
from api.dependencies import get_current_user



router = APIRouter(prefix="/user_tool", tags=["User Tool Status"])


@router.patch("/status")
async def update_user_tool_status(
    patch: UserToolStatus,  # enum ( 'allowed', 'denied' ) and {"tool_id": 33}
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    enum ( 'allowed', 'denied' ) You can choose
    and tool_id also
    """

    stmt = (
        update(UserTool)
        .where(UserTool.user_id == user.id, UserTool.tool_id == patch.tool_id,)
        .values(status = patch.status)
    )
    await db.execute(stmt)
    await db.commit()
    return {"ok": True}