# services/message_service.py
from typing import List, Union, Optional
from fastapi import Depends, Request
import httpx
from sqlalchemy import select
from core.config import INTERNAL_BASE_URL, INTERNAL_TIMEOUT, RAG_TOP_K
from sqlalchemy.ext.asyncio import AsyncSession
from core.database import get_db
from db.models import Message, QueryProvenance
from services.vector_db_faiss import FAISSVectorDB
from db.models import Message
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


async def create_or_update_message(
    thread_id: str,
    role: str,
    content: str,
    image_url: Optional[str] = None,
    json_metadata: Optional[dict] = None,
    tool_call: Optional[List[str]] = None,
    message_id: Optional[int] = None,
    vector_db: FAISSVectorDB = Depends(FAISSVectorDB.get_instance),
    db: AsyncSession = Depends(get_db),
) -> Message:
    """
    Create new message OR update existing one.
    Handles RAG provenance if tool_call == "rag_tool"
    """
    if message_id:
        # Update existing message
        result = await db.execute(select(Message).where(Message.id == message_id))
        db_message = result.scalar_one()
    else:
        # Create new
        db_message = Message(
            thread_id=thread_id,
            role=role,
            content=content,
            image_url=image_url,
            json_metadata=json_metadata,
        )
        db.add(db_message)

    # Always update these fields
    db_message.content = content
    db_message.image_url = image_url
    db_message.json_metadata = json_metadata

    await db.flush()  # Ensures .id is available

    # Handle RAG only on creation (or if explicitly needed)
    if tool_call and "rag_tool" in tool_call:
        try:
            hits = await vector_db.query(
                thread_id=thread_id,
                query=content,
                top_k=RAG_TOP_K
            )
            for hit in hits:
                chunk_id = int(hit["metadata"]["chunk_id"])
                db.add(QueryProvenance(
                    message_id=db_message.id,
                    chunk_id=chunk_id,
                    score=hit["score"],
                ))
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
        except Exception as e:
            logger.warning(f"RAG failed for message {db_message.id}: {e}")

    await db.commit()
    await db.refresh(db_message)
    return db_message


async def create_message_by_api(
    *,
    request: Request,
    thread_id: str,
    role: str,
    content: str,
    image_url: str | None = None,
    json_metadata: dict | list | None = None,
    tool_call: Union[str, List[str], None] = None,
) -> Message:
    """
    Persist a message via internal HTTP call /messages/create
    so we keep a single source of truth (same validations, same RAG logic).
    """
    base   = INTERNAL_BASE_URL.rstrip("/")
    url    = f"{base}/messages/create"
    payload = {
        "thread_id": thread_id,
        "role": role,
        "content": content,
        "image_url": image_url,
        "json_metadata": json_metadata,
        "tool_call": tool_call,
    }

    timeout = httpx.Timeout(INTERNAL_TIMEOUT)
    async with httpx.AsyncClient(timeout=timeout, cookies=request.cookies) as client:
        try:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            # log and re-raise so caller can react
            raise RuntimeError(f"Failed to create message via API: {exc}") from exc

    # response body is MessageRead (same fields we need)
    data = resp.json()
    # convert to ORM instance if you need it; here we just return a dummy
    # with the keys we care about
    return Message(
        id=data["id"],
        thread_id=data["thread_id"],
        role=data["role"],
        content=data["content"],
        image_url=data["image_url"],
        json_metadata=data.get("json_metadata"),
        created_at=datetime.fromisoformat(data["created_at"]),
    )