from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from sqlalchemy.orm import selectinload
from typing import List
from core.database import get_db
from db.models import Thread, User, Document, Message
from api.schemas.thread import ThreadCreate, ThreadRead, ThreadDelete
from pydantic import UUID4
from services.vector_db_faiss import FAISSVectorDB
from api.dependencies import get_current_user
from pathlib import Path
import logging
import uuid

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/threads", tags=["Threads"])



# ---------- create ----------
@router.post("/create", response_model=ThreadRead, status_code=201)
async def create_thread(
    body: ThreadCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    # 1. Insert
    db_thread = Thread(
        id=str(uuid.uuid4()),
        user_id=user.id,
        title=body.title.strip(),
    )

    db.add(db_thread)
    await db.commit()
    await db.refresh(db_thread)

    # 2. RELOAD with selectinload
    stmt = (
        select(Thread)
        .where(Thread.id == db_thread.id)
        .options(
            selectinload(Thread.messages)  # important!!
        )
    )
    result = await db.execute(stmt)
    thread = result.scalar_one()

    return thread


# ---------- list all (scrolling ready) ----------
@router.get("/show_all", response_model=List[ThreadRead])
async def list_threads(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Return every thread for the current user (scrolling-friendly)."""
    
    stmt = (
        select(Thread)
        .where(Thread.user_id == user.id)
        .options(
            selectinload(Thread.messages)  # important!!
        )
        .order_by(Thread.created_at.desc())
    )
  
    result = await db.execute(stmt)
    return result.scalars().all()


# ---------- single thread + messages ----------
@router.get("/show/{thread_id}", response_model=ThreadRead)
async def get_thread(
    thread_id: UUID4,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Return thread with messages pre-loaded (oldest → newest)."""
    stmt = (
        select(Thread)
        .where(Thread.id == str(thread_id), Thread.user_id == user.id)
        .options(
            selectinload(Thread.messages).load_only(
                Message.id,
                Message.thread_id,
                Message.role,
                Message.content,
                Message.json_metadata,
                Message.created_at,
            )
        )
    )

    result = await db.execute(stmt)
    thread = result.scalar_one_or_none()
    if not thread:
        raise HTTPException(404, "Thread not found")

    # sort messages in-memory (async-safe)
    thread.messages.sort(key=lambda m: m.created_at)
    return thread


@router.delete("/delete/{thread_id}", response_model=ThreadDelete)
async def delete_thread(
    thread_id: UUID4,
    db: AsyncSession = Depends(get_db),
    vector_db: FAISSVectorDB = Depends(FAISSVectorDB.get_instance),
    user: User = Depends(get_current_user),
):
    try:
        # 1. fetch thread (async)
        stmt = select(Thread).where(
            Thread.id == str(thread_id),
            Thread.user_id == user.id
        )
        result = await db.execute(stmt)
        thread = result.scalar_one_or_none()

        if not thread:
            raise HTTPException(404, "Thread not found or not yours")

        # 2. fetch documents (async)
        docs_stmt = select(Document).where(Document.thread_id == str(thread_id))
        docs = (await db.execute(docs_stmt)).scalars().all()

        file_count = 0
        for doc in docs:
            try:
                Path(doc.file_path).unlink(missing_ok=True)
                file_count += 1
            except Exception as exc:
                logger.warning("Could not delete file %s: %s", doc.file_path, exc)

        # 3. delete vector index
        index_removed = False
        if vector_db.exists(str(thread_id)):
            vector_db.delete_thread_index(str(thread_id))
            index_removed = True

        # 4. cascade delete child rows
        await db.execute(
            delete(Document).where(Document.thread_id == str(thread_id))
        )
        await db.execute(
            delete(Message).where(Message.thread_id == str(thread_id))
        )

        # 5. delete parent row
        await db.delete(thread)

        # 6. commit
        await db.commit()

    except Exception:
        await db.rollback()
        raise

    return ThreadDelete(
        thread_id=thread_id,
        deleted_documents=file_count,
        vector_index_removed=index_removed,
    )