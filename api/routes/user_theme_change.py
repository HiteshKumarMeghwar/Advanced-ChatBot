from fastapi import APIRouter, Depends
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession
from db.models import User, UserSettings
from core.database import get_db
from api.schemas.user_theme_change import UserThemeChange
from api.dependencies import get_current_user



router = APIRouter(prefix="/user_theme", tags=["User Theme Change"])


@router.patch("/change")
async def update_user_tool_status(
    patch: UserThemeChange,  # string
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    String value change ( light or dark )
    """

    stmt = (
        update(UserSettings)
        .where(UserSettings.user_id == user.id)
        .values(theme = patch.theme)
    )
    await db.execute(stmt)
    await db.commit()
    return {"ok": True}