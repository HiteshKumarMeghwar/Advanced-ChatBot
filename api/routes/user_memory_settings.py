from fastapi import APIRouter, Depends
from api.dependencies import get_current_user
from core.config import USER_MEMORY_DEFAULTS
from sqlalchemy.ext.asyncio import AsyncSession
from core.database import get_db
from pydantic import BaseModel
from db.models import User, UserMemorySetting
from sqlalchemy import select

router = APIRouter(prefix="/memory", tags=["memory"])

class MemoryUpdate(BaseModel):
    allow_episodic: bool | None = None
    allow_semantic: bool | None = None
    allow_procedural: bool | None = None
    semantic_retention_days: int | None = None

@router.get("/get_settings")
async def get_settings(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    row = await db.scalar(select(UserMemorySetting).filter_by(user_id=user.id))
    if not row:
        return USER_MEMORY_DEFAULTS
    return {
        "allow_episodic": row.allow_episodic,
        "allow_semantic": row.allow_semantic,
        "allow_procedural": row.allow_procedural,
        "semantic_retention_days": row.semantic_retention_days
    }

@router.post("/update")
async def update_settings(
    payload: MemoryUpdate, 
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    row = await db.scalar(select(UserMemorySetting).filter_by(user_id=user.id))
    if row:
        if payload.allow_semantic is not None: row.allow_semantic = payload.allow_semantic
        if payload.allow_episodic is not None: row.allow_episodic = payload.allow_episodic
        if payload.allow_procedural is not None: row.allow_procedural = payload.allow_procedural
        if payload.semantic_retention_days is not None: row.semantic_retention_days = payload.semantic_retention_days
    else:
        row = UserMemorySetting(user_id=user.id,
                                allow_episodic=payload.allow_episodic if payload.allow_episodic is not None else True,
                                allow_semantic=payload.allow_semantic if payload.allow_semantic is not None else True,
                                allow_procedural=payload.allow_procedural if payload.allow_procedural is not None else True,
                                semantic_retention_days=payload.semantic_retention_days if payload.semantic_retention_days is not None else SEMANTIC_DECAY_DAYS)
        db.add(row)
    await db.commit()
    return {"ok": True}
