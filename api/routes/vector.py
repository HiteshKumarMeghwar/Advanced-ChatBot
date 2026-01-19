from fastapi import APIRouter, Depends, HTTPException, status
from typing import List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from core.database import get_db
import logging
import aiofiles.os

# from services.vector_db_faiss import FAISSVectorDB
from services.vector_db_qdrant_rag import QdrantVectorDBRAG
from api.dependencies import get_current_user
from db.models import User, Document
from core.config import RAG_TOP_K
logger = logging.getLogger(__name__)


router = APIRouter(prefix="/vector", tags=["Vector"])


# ──────────────────────────────────────────────────────────────
#                    SEMANTIC SEARCH (RAG)
# ──────────────────────────────────────────────────────────────
@router.get("/semantic_search/{thread_id}", response_model=List[dict])
async def search_thread(
    thread_id: str,
    q: str,
    top_k: int = RAG_TOP_K,
    min_score: float = 0.0,
    vector_db: QdrantVectorDBRAG = Depends(QdrantVectorDBRAG.get_instance),
    user: User = Depends(get_current_user),
):
    """Semantic search inside a single thread."""
    results = await vector_db.query(
        user_id=user.id,
        thread_id=str(thread_id),
        query_text=q, 
        top_k=top_k,
        min_score=min_score,
    )
    if not results:
        logger.info("No relevant chunks found for thread %s, query: %s", thread_id, q)
    return results



# ──────────────────────────────────────────────────────────────
#                    DELETE SINGLE DOCUMENT VECTORS
# ──────────────────────────────────────────────────────────────
@router.delete("/delete/{thread_id}/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    thread_id: str,
    document_id: int,
    db: AsyncSession = Depends(get_db),
    vector_db: QdrantVectorDBRAG = Depends(QdrantVectorDBRAG.get_instance),
    user: User = Depends(get_current_user),
):
    """Delete document row, physical file, and its vector chunks (whole thread index)."""
    
    # verify ownership
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

    # delete physical file
    try:
        await aiofiles.os.remove(doc.file_path)
    except Exception as exc:
        logger.warning("Could not delete file %s: %s", doc.file_path, exc)
        # continue anyway – file may already be gone

    # Delete vectors belonging to this document
    try:
        deleted_count = await vector_db.delete_document(
            user_id=user.id,
            thread_id=thread_id,
            document_id=document_id
        )

        logger.info(
            "Deleted %d vector chunks for document %d in thread %s (user %d)",
            deleted_count, document_id, thread_id, user.id
        )

        # delete DB row (cascade removes DocumentChunk rows if FK is ON DELETE CASCADE)
        db.delete(doc)
        await db.commit()

    except Exception as exc:
        logger.exception("Failed to delete document vectors")
        raise HTTPException(
            status_code=500,
            detail="Failed to delete vector embeddings"
        )


# ---------- existence check ----------
@router.head("/exists_index/{thread_id}", status_code=status.HTTP_200_OK)
async def index_exists(
    thread_id: str,
    vector_db: QdrantVectorDBRAG = Depends(QdrantVectorDBRAG.get_instance),
    user: User = Depends(get_current_user),
):
    """Return 200 if index exists, 404 otherwise."""
    
    exists = await vector_db.thread_has_vectors(
        user_id=user.id,
        thread_id=thread_id
    )

    if not exists:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No vector index found for this thread"
        )

    return None  # 200 OK - index exists