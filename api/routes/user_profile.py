from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import joinedload
from sqlalchemy.ext.asyncio import AsyncSession
from db.models import User, UserTool
from core.database import get_db
from api.schemas.user_profile import UserProfile
from api.dependencies import get_current_user

router = APIRouter(prefix="/user", tags=["User"])


@router.get("/profile", response_model=UserProfile)
async def get_user_profile(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    stmt = (
        select(User)
        .where(User.id == user.id)
        .options(
            joinedload(User.settings),
            joinedload(User.threads),
            joinedload(User.documents),
            joinedload(User.tools).joinedload(UserTool.tool)
        )
    )
    result = await db.execute(stmt)
    db_user = result.unique().scalar_one_or_none()
    
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")

    # Convert UserTool → Tool list
    tools_list = [ut.tool for ut in db_user.tools]

    return UserProfile(
        id=db_user.id,
        name=db_user.name,
        email=db_user.email,
        created_at=str(db_user.created_at),
        threads=db_user.threads,
        documents=db_user.documents,
        settings=db_user.settings,
        tools=tools_list
    )