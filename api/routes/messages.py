from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
from core.database import get_db
from sqlalchemy import select
from db.models import Message, QueryProvenance
from api.schemas.message import MessageCreate, MessageRead
from services.vector_db_faiss import FAISSVectorDB
from api.dependencies import get_current_user
from core.config import RAG_TOP_K

router = APIRouter(prefix="/messages", tags=["Messages"])

@router.post("/create", response_model=MessageRead)
async def create_message(
    message: MessageCreate,
    db: AsyncSession = Depends(get_db),
    vector_db: FAISSVectorDB = Depends(FAISSVectorDB.get_instance),
    user=Depends(get_current_user),   # JWT
):
    """
    Normal chat OR RAG chat (when tool_call=True).
    If RAG is used we fill QueryProvenance (citations).
    """
    
    # Ensure tool_call is a list for consistency
    if isinstance(message.tool_call, str):
        tool_calls = [message.tool_call]
    else:
        tool_calls = message.tool_call or []

    # 1. save the user/assistant message
    db_message = Message(
        thread_id=message.thread_id,
        role=message.role,
        content=message.content,
        json_metadata=message.json_metadata,
    )
    db.add(db_message)
    await db.flush()          # gives us .id

    # 2. RAG branch
    if message.tool_call == "rag_tool":
        hits = await vector_db.query(
            thread_id=message.thread_id,
            query=message.content,
            top_k=RAG_TOP_K
        )
        # 3. write provenance (one row per retrieved chunk)
        for hit in hits:
            chunk_id = int(hit["metadata"]["chunk_id"])
            db.add(QueryProvenance(
                message_id=db_message.id,
                chunk_id=chunk_id,
                score=hit["score"],
            ))
        # optional: embed the citation list inside json_metadata
        db_message.json_metadata = {
            "citations": [
                {
                    "chunk_id": int(h["metadata"]["chunk_id"]),
                    "document_id": int(h["metadata"]["document_id"]),
                    "score": float(h["score"]),
                    "source": h["metadata"].get("source", ""),
                }
                for h in hits
            ]
        }

    await db.commit()
    await db.refresh(db_message)
    return db_message

@router.get("/show/{thread_id}", response_model=List[MessageRead])
async def get_thread_messages(thread_id: str, db: AsyncSession = Depends(get_db)):
    stmt = (
        select(Message)
        .where(Message.thread_id == thread_id)
        .order_by(Message.created_at.desc())
    )
    result = await db.execute(stmt)
    return result.scalars().all()
