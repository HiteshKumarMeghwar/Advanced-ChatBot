from fastapi import APIRouter, Depends
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession
from db.models import User, UserSettings
from core.database import get_db
from api.schemas.notification_status import NotificationStaus
from api.dependencies import get_current_user



router = APIRouter(prefix="/user_notification", tags=["User Notifications"])


@router.patch("/status")
async def update_user_notification_status(
    patch: NotificationStaus,  # bool
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Boolean ( true/false ) You can choose
    """
    stmt = (
        update(UserSettings)
        .where(UserSettings.user_id == user.id)
        .values(notification_enabled=patch.notification_enabled)
    )
    await db.execute(stmt)
    await db.commit()
    return {"ok": True}