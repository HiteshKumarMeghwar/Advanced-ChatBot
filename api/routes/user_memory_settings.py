from typing import List, Literal
from fastapi import APIRouter, Body, Depends, HTTPException
from api.dependencies import get_current_user
from core.config import SEMANTIC_DECAY_DAYS, USER_MEMORY_DEFAULTS
from sqlalchemy.ext.asyncio import AsyncSession
from core.database import get_db
from pydantic import BaseModel
from db.models import EpisodicMemory, ProceduralMemory, SemanticMemory, User, UserMemorySetting
from sqlalchemy import delete, not_, select, update
from services.memory_metrics import (
    MEMORY_EXTRACTION_TOTAL,
    MEMORY_EXTRACTION_FAILURES,
    SEMANTIC_SAVE_TOTAL,
    SEMANTIC_VERSIONED_TOTAL,
    PII_ENCRYPTED_TOTAL,
)

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


@router.get("/metrics")
async def memory_metrics(user: User = Depends(get_current_user)):
    return {
        "extraction_total": MEMORY_EXTRACTION_TOTAL._value.get(),
        "extraction_failures": MEMORY_EXTRACTION_FAILURES._value.get(),
        "semantic_saved": {
            "encrypted": SEMANTIC_SAVE_TOTAL.labels(encrypted="true")._value.get(),
            "plaintext": SEMANTIC_SAVE_TOTAL.labels(encrypted="false")._value.get(),
        },
        "semantic_versioned": SEMANTIC_VERSIONED_TOTAL._value.get(),
        "pii_encrypted": {
            k[0]: v._value.get()
            for k, v in PII_ENCRYPTED_TOTAL._metrics.items()
        },
    }


@router.get("/user_memory_settings")
async def get_memory_settings(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    stmt = select(UserMemorySetting).where(UserMemorySetting.user_id == user.id)
    result = await db.execute(stmt)
    settings = result.scalar_one_or_none()

    # 🔐 AUTO-BOOTSTRAP (enterprise standard)
    if not settings:
        settings = UserMemorySetting(
            user_id=user.id,
            **USER_MEMORY_DEFAULTS,
        )
        db.add(settings)
        await db.commit()
        await db.refresh(settings)

    return {
        "allow_episodic": settings.allow_episodic,
        "allow_semantic": settings.allow_semantic,
        "allow_procedural": settings.allow_procedural,
        "allow_long_conversation_memory": settings.allow_long_conversation_memory,
        "semantic_retention_days": settings.semantic_retention_days,
    }


# ---------- episodic ----------
@router.get("/episodic/recent")
async def recent_episodic(
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    stmt = (
        select(EpisodicMemory)
        .where(EpisodicMemory.user_id == user.id)
        .order_by(EpisodicMemory.created_at.desc())
        .limit(limit)
    )
    rows = (await db.execute(stmt)).scalars().all()
    return rows


@router.patch("/episodic/{id}/disable")
async def disable_episodic(
    id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    stmt = (
        update(EpisodicMemory)
        .where(EpisodicMemory.id == id, EpisodicMemory.user_id == user.id)
        .values(active=False)
        .returning(EpisodicMemory)
    )
    obj = (await db.execute(stmt)).scalar_one_or_none()
    if not obj:
        raise HTTPException(status_code=404, detail="Episodic memory not found")
    await db.commit()
    return obj


@router.delete("/episodic/{id}")
async def delete_episodic(
    id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    stmt = delete(EpisodicMemory).where(
        EpisodicMemory.id == id,
        EpisodicMemory.user_id == user.id,
    )
    res = await db.execute(stmt)
    if res.rowcount == 0:
        raise HTTPException(status_code=404, detail="Not found")
    await db.commit()
    return {"ok": True}


# ---------- semantic ----------
@router.get("/semantic")
async def semantic_memories(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    stmt = select(SemanticMemory).where(
        SemanticMemory.user_id == user.id,
        SemanticMemory.active == True,
    )
    return (await db.execute(stmt)).scalars().all()


@router.patch("/semantic/{id}/disable")
async def disable_semantic(
    id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    stmt = (
        update(SemanticMemory)
        .where(
            SemanticMemory.id == id,
            SemanticMemory.user_id == user.id,
            SemanticMemory.active == True,
        )
        .values(active=False)
        .returning(SemanticMemory)
    )
    obj = (await db.execute(stmt)).scalar_one_or_none()
    if not obj:
        raise HTTPException(status_code=404, detail="Semantic memory not found")
    await db.commit()
    return obj


@router.delete("/semantic/{id}")
async def delete_semantic(
    id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    stmt = delete(SemanticMemory).where(
        SemanticMemory.id == id,
        SemanticMemory.user_id == user.id,
    )
    res = await db.execute(stmt)
    if res.rowcount == 0:
        raise HTTPException(status_code=404, detail="Semantic memory not found")
    await db.commit()
    return {"ok": True}


# ---------- procedural ----------
@router.get("/procedural")
async def procedural_rules(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    stmt = select(ProceduralMemory).where(
        ProceduralMemory.user_id == user.id,
        ProceduralMemory.active == True,
    )
    return (await db.execute(stmt)).scalars().all()


@router.patch("/procedural/{id}/disable")
async def disable_procedural(
    id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    stmt = (
        update(ProceduralMemory)
        .where(
            ProceduralMemory.id == id,
            ProceduralMemory.user_id == user.id,
            ProceduralMemory.active == True,
        )
        .values(active=False)
        .returning(ProceduralMemory)
    )
    obj = (await db.execute(stmt)).scalar_one_or_none()
    if not obj:
        raise HTTPException(status_code=404, detail="Procedural memory not found")
    await db.commit()
    return obj


@router.delete("/procedural/{id}")
async def delete_procedural(
    id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    stmt = delete(ProceduralMemory).where(
        ProceduralMemory.id == id,
        ProceduralMemory.user_id == user.id,
    )
    res = await db.execute(stmt)
    if res.rowcount == 0:
        raise HTTPException(status_code=404, detail="Procedural memory not found")
    await db.commit()
    return {"ok": True}


# ---------- user memory toggles ----------
@router.patch("/toggle/{field}")
async def toggle_memory_setting(
    field: Literal[
        "allow_episodic",
        "allow_semantic",
        "allow_procedural",
        "allow_long_conversation_memory",
    ],
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    stmt = select(UserMemorySetting).where(UserMemorySetting.user_id == user.id)
    result = await db.execute(stmt)
    settings = result.scalar_one_or_none()

    if not settings:
        settings = UserMemorySetting(user_id=user.id)
        db.add(settings)
        await db.flush()

    current = getattr(settings, field)
    new_val = not current
    setattr(settings, field, new_val)

    await db.commit()
    return {"field": field, "enabled": new_val}




# ---------- bulk / wipe helpers ----------
MEMORY_MODELS = {
    "episodic": EpisodicMemory,
    "semantic": SemanticMemory,
    "procedural": ProceduralMemory,
}

def _get_model(type_: str):
    if type_ not in MEMORY_MODELS:
        raise HTTPException(status_code=400, detail="Invalid memory type")
    return MEMORY_MODELS[type_]

@router.post("/{memory_type}/delete_all")
async def delete_all_memories(
    memory_type: Literal["episodic", "semantic", "procedural"],
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    model = _get_model(memory_type)
    await db.execute(
        delete(model).where(model.user_id == user.id)
    )
    await db.commit()
    return {"ok": True}


# POST /{type}/delete_selected   {"ids": number[]}
class IdsPayload(BaseModel):
    ids: List[int]

@router.post("/{memory_type}/delete_selected")
async def delete_selected_memories(
    memory_type: Literal["episodic", "semantic", "procedural"],
    payload: IdsPayload = Body(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    model = _get_model(memory_type)
    res = await db.execute(
        delete(model).where(
            model.user_id == user.id,
            model.id.in_(payload.ids)
        )
    )
    await db.commit()
    return {"deleted": res.rowcount}
