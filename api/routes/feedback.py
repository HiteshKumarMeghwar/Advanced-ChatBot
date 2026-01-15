# routers/feedback.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import insert
from pydantic import BaseModel
from core.config import CHAT_MODEL_SMALLEST_8B
from core.database import get_db
from api.dependencies import get_current_user
from db.models import MessageFeedback, User
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/feedback", tags=["Feedback"])

class FeedbackIn(BaseModel):
    message_id: int
    rating: str  # "up" | "down"
    reason: str | None = None
    model: str | None = None
    tool_used: str | None = None
    latency_ms: float | None = None

@router.post("/user_feedback")
async def save_feedback(
    body: FeedbackIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    stmt = insert(MessageFeedback).values(
        user_id=user.id,
        message_id=body.message_id,
        rating=body.rating,
        reason=body.reason.strip() if body.reason else None,
        model=CHAT_MODEL_SMALLEST_8B,
        tool_used=body.tool_used,
        latency_ms=body.latency_ms
    )
    await db.execute(stmt)
    await db.commit()
    return {"status": "saved"}