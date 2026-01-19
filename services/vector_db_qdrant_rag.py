# services/vector_db_qdrant_rag.py
"""
Qdrant vector store — ONLY for RAG / thread-based uploaded documents
No semantic memory, no local file-system indexes
"""

import logging
from typing import List, Dict

from qdrant_client import QdrantClient
from qdrant_client.models import (
    PointStruct,
    VectorParams,
    Distance,
    Filter,
    FieldCondition,
    MatchValue,
    QueryResponse,
)

from langchain_core.documents import Document as LCDocument
from services.embeddings import EmbeddingsCreator
from core.config import (
    COLLECTION_RAG,
    EMBEDDING_MODEL,
    QDRANT_CLIENT_URL,
    RAG_TOP_K,
)
from db.models import EmbeddingMetadata
from sqlalchemy.ext.asyncio import AsyncSession
import uuid

logger = logging.getLogger(__name__)


class QdrantVectorDBRAG:
    _instance = None

    def __init__(self):
        self.client = QdrantClient(url=QDRANT_CLIENT_URL)
        self.embedder = EmbeddingsCreator(EMBEDDING_MODEL).model
        self._ensure_collection()

    @classmethod
    def get_instance(cls) -> "QdrantVectorDBRAG":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _get_vector_size(self) -> int:
        return len(self.embedder.embed_query("size_probe"))

    def _ensure_collection(self):
        collections = self.client.get_collections().collections
        if COLLECTION_RAG not in {c.name for c in collections}:
            self.client.create_collection(
                collection_name=COLLECTION_RAG,
                vectors_config=VectorParams(
                    size=self._get_vector_size(),
                    distance=Distance.COSINE,
                ),
            )
            logger.info(f"Created Qdrant RAG collection: {COLLECTION_RAG}")

    async def add_documents(
        self,
        user_id: int,
        thread_id: str,
        documents: List[LCDocument],
        db: AsyncSession,
    ) -> int:
        """Add document chunks — scoped by user + thread"""
        points = []

        for doc in documents:
            vector = self.embedder.embed_query(doc.page_content)
            point_id = str(uuid.uuid4())   # or doc.metadata.get("chunk_id")

            payload = {
                "user_id": user_id,
                "thread_id": thread_id,
                "content": doc.page_content,
                **doc.metadata,
            }

            points.append(
                PointStruct(
                    id=point_id,
                    vector=vector,
                    payload=payload,
                )
            )

            # Optional: keep chunk → vector mapping in SQL
            chunk_id = doc.metadata.get("chunk_id")
            if chunk_id:
                db.add(
                    EmbeddingMetadata(
                        chunk_id=int(chunk_id),
                        vector_id=point_id,
                        embedding_model=EMBEDDING_MODEL,
                    )
                )

        if points:
            self.client.upsert(collection_name=COLLECTION_RAG, points=points)

        if db.in_transaction():
            await db.commit()

        logger.info("Stored %d chunks for user %d / thread %s", len(points), user_id, thread_id)
        return len(points)

    async def query(
        self,
        user_id: int,
        thread_id: str,
        query_text: str,
        top_k: int = RAG_TOP_K,
        min_score: float = 0.0,
    ) -> List[Dict]:
        """Search only inside one user's thread"""
        embedding = self.embedder.embed_query(query_text)

        response: QueryResponse = self.client.query_points(
            collection_name=COLLECTION_RAG,
            query=embedding,
            query_filter=Filter(
                must=[
                    FieldCondition(key="user_id",   match=MatchValue(value=user_id)),
                    FieldCondition(key="thread_id", match=MatchValue(value=thread_id)),
                ]
            ),
            limit=top_k,
            with_payload=True,
            score_threshold=min_score,
        )

        return [
            {
                "content": p.payload.get("content", ""),
                "metadata": {
                    k: v for k, v in (p.payload or {}).items()
                    if k not in ("content", "user_id", "thread_id")
                },
                "score": float(p.score),
            }
            for p in response.points
            if p.payload
        ]

    async def delete_thread(
        self,
        user_id: int,
        thread_id: str,
    ) -> int:
        """Delete everything in one thread (all documents)"""
        result = self.client.delete(
            collection_name=COLLECTION_RAG,
            points_selector=Filter(
                must=[
                    FieldCondition(key="user_id",   match=MatchValue(value=user_id)),
                    FieldCondition(key="thread_id", match=MatchValue(value=thread_id)),
                ]
            ),
        )
        deleted_count = result.result.deleted if hasattr(result, 'result') and hasattr(result.result, 'deleted') else 0
        logger.info("Deleted %d points for user %d / thread %s", deleted_count, user_id, thread_id)
        return deleted_count

    async def delete_document(
        self,
        user_id: int,
        thread_id: str,
        document_id: int | str,
    ) -> int:
        """Delete only chunks of one specific document"""
        result = self.client.delete(
            collection_name=COLLECTION_RAG,
            points_selector=Filter(
                must=[
                    FieldCondition(key="user_id",     match=MatchValue(value=user_id)),
                    FieldCondition(key="thread_id",   match=MatchValue(value=thread_id)),
                    FieldCondition(key="document_id", match=MatchValue(value=str(document_id))),
                ]
            ),
        )
        deleted_count = result.result.deleted if hasattr(result, 'result') and hasattr(result.result, 'deleted') else 0
        logger.info("Deleted %d chunks of doc %s (u:%d / t:%s)", deleted_count, document_id, user_id, thread_id)
        return deleted_count

    async def thread_has_vectors(
        self,
        user_id: int,
        thread_id: str,
    ) -> bool:
        """Quick existence check for thread"""
        count = self.client.count(
            collection_name=COLLECTION_RAG,
            count_filter=Filter(
                must=[
                    FieldCondition(key="user_id",   match=MatchValue(value=user_id)),
                    FieldCondition(key="thread_id", match=MatchValue(value=thread_id)),
                ]
            ),
            exact=True,
        )
        return count.count > 0