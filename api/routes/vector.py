from fastapi import APIRouter, Depends, HTTPException, status
from typing import List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from core.database import get_db
import logging
import aiofiles.os

from services.vector_db_faiss import FAISSVectorDB
from api.dependencies import get_current_user
from db.models import User, Document
from core.config import RAG_TOP_K
logger = logging.getLogger(__name__)


router = APIRouter(prefix="/vector", tags=["Vector"])


# ---------- search ----------
@router.get("/semantic_search/{thread_id}", response_model=List[dict])
async def search_thread(
    thread_id: str,
    q: str,
    top_k: int = RAG_TOP_K,
    vector_db: FAISSVectorDB = Depends(FAISSVectorDB.get_instance),
    user: User = Depends(get_current_user),
):
    """Semantic search inside a single thread."""
    results = await vector_db.query(str(thread_id), q, top_k)
    return results


# ---------- delete index ----------
@router.delete("/delete/{thread_id}/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    thread_id: str,
    document_id: int,
    db: AsyncSession = Depends(get_db),
    vector_db: FAISSVectorDB = Depends(FAISSVectorDB.get_instance),
    user: User = Depends(get_current_user),
):
    """Delete document row, physical file, and its vector chunks (whole thread index)."""
    
    # 1. verify ownership
    doc = (
        await db.execute(
            select(Document)
            .where(
                Document.id == document_id,
                Document.thread_id == str(thread_id),
                Document.user_id == user.id
            )
            .with_for_update()          # SELECT ... FOR UPDATE
            .limit(1)
        )
    )
    if not doc:
        raise HTTPException(404, "Document not found or not yours")

    # 2. delete physical file
    try:
        await aiofiles.os.remove(doc.file_path)
    except Exception as exc:
        logger.warning("Could not delete file %s: %s", doc.file_path, exc)
        # continue anyway – file may already be gone

    # 3. delete vector index (whole thread – optional: change to chunk-level later)
    if await vector_db.exists(str(thread_id)):
        await vector_db.delete_thread_index(str(thread_id))

    # 4. delete DB row (cascade removes DocumentChunk rows if FK is ON DELETE CASCADE)
    db.delete(doc)
    await db.commit()


# ---------- existence check ----------
@router.head("/exists_index/{thread_id}", status_code=status.HTTP_200_OK)
async def index_exists(
    thread_id: str,
    vector_db: FAISSVectorDB = Depends(FAISSVectorDB.get_instance),
    user: User = Depends(get_current_user),
):
    """Return 200 if index exists, 404 otherwise."""
    if not await vector_db.exists(str(thread_id)):
        raise HTTPException(404, "Index not found")