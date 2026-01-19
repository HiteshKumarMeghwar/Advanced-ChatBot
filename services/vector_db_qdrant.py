# services/vector_db_qdrant.py
from typing import List
from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct
from qdrant_client.models import QueryResponse
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession as DBSession
from qdrant_client.models import (
    VectorParams,
    Distance,
    Filter,
    FieldCondition,
    MatchValue,
    Range,
)
from langchain_core.documents import Document
from db.models import SemanticEmbedding
from services.embeddings import EmbeddingsCreator
from core.config import COLLECTION_SEMANTIC_MEMORY, EMBEDDING_MODEL, QDRANT_CLIENT_URL, RAG_TOP_K, SEMANTIC_TOP_K
import uuid
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class QdrantVectorDB:
    _instance = None

    def __init__(self):
        self.client = QdrantClient(url=QDRANT_CLIENT_URL)
        self.embedder = EmbeddingsCreator(EMBEDDING_MODEL).model

        self._ensure_collection()

    @classmethod
    def get_instance(cls):
        if not cls._instance:
            cls._instance = cls()
        return cls._instance
    
    def _get_vector_size(self) -> int:
        vec = self.embedder.embed_query("dimension_probe")
        return len(vec)

    def _ensure_collection(self):
        collections = self.client.get_collections().collections
        vector_size = self._get_vector_size()
        if COLLECTION_SEMANTIC_MEMORY not in {c.name for c in collections}:
            self.client.create_collection(
                collection_name=COLLECTION_SEMANTIC_MEMORY,
                vectors_config=VectorParams(
                    size=vector_size,
                    distance=Distance.COSINE,
                ),
            )

    # ----------------------------------------------------
    # ADD SEMANTIC MEMORY
    # ----------------------------------------------------
    async def add_semantic_documents(
        self, 
        user_id: int, 
        documents: list[Document],
        db: DBSession,
    ):
        try:
            self.client.upsert(
                collection_name=COLLECTION_SEMANTIC_MEMORY,
                points=[
                    PointStruct(
                        id=doc.metadata["embedding_id"],
                        vector=self.embedder.embed_query(doc.page_content),
                        payload={
                            "user_id": user_id,
                            **doc.metadata,                    # ← very convenient!
                            "content": doc.page_content,
                        }
                    )
                    for doc in documents
                ]
            )
            
            for doc in documents:
                db.add(
                    SemanticEmbedding(
                        user_id=user_id,
                        vector_id=doc.metadata['embedding_id'],
                        embedding_model=EMBEDDING_MODEL,
                        semantic_memory_id=doc.metadata["saved_semantic_id"],
                    )
                )

            await db.commit()
            
        except Exception as exc:
            logger.exception("Semantic vector write failed for user %s", user_id)
            raise RuntimeError("Semantic vector index update failed") from exc

    # ----------------------------------------------------
    # QUERY (VIP SEMANTIC SEARCH)
    # ----------------------------------------------------
    async def query(
        self,
        user_id: int,
        query: str,
        top_k: int = SEMANTIC_TOP_K,
        pii: bool | None = None,
    ):
        embedding = self.embedder.embed_query(query)
        now_ts = datetime.now(timezone.utc).timestamp()

        must = [
            FieldCondition(key="user_id", match=MatchValue(value=user_id)),
            FieldCondition(key="retention_until", range=Range(gt=now_ts)),
        ]
        if pii is not None:
            must.append(FieldCondition(key="pii", match=MatchValue(value=pii)))

        response: QueryResponse = self.client.query_points(
            collection_name=COLLECTION_SEMANTIC_MEMORY,
            query=embedding,
            query_filter=Filter(must=must),
            limit=top_k,
            with_payload=True,
        )

        return [
            {
                "content": point.payload.get("content", ""),
                "metadata": point.payload or {},
                "score": point.score,
            }
            for point in response.points
            if point.payload is not None
        ]
    # ----------------------------------------------------
    # DELETE (TRUE DELETE, NO REBUILD)
    # ----------------------------------------------------
    async def delete_by_embedding_ids(self, user_id: int, embedding_ids: list[str]):
        self.client.delete(
            collection_name=COLLECTION_SEMANTIC_MEMORY,
            points_selector=Filter(
                must=[
                    FieldCondition(
                        key="embedding_id",
                        match=MatchValue(any=embedding_ids),
                    ),
                    FieldCondition(
                        key="user_id",
                        match=MatchValue(value=user_id),
                    ),
                ]
            ),
        )


    async def delete_semantic_embeddings(self, user_id: int, embedding_ids: List[str], db: DBSession):
        """
        Delete semantic embeddings rows and then rebuild index for the user.
        Because FAISS deletion is non-trivial, we rebuild the index from remaining docs.
        """
        if not embedding_ids:
            return
        try:

            # Remove SemanticEmbedding rows first
            await db.execute(delete(SemanticEmbedding).where(SemanticEmbedding.vector_id.in_(embedding_ids)))

            self.client.delete(
                collection_name=COLLECTION_SEMANTIC_MEMORY,
                points_selector=Filter(
                    must=[
                        FieldCondition(
                            key="embedding_id",
                            match=MatchValue(any=embedding_ids),
                        ),
                        FieldCondition(
                            key="user_id",
                            match=MatchValue(value=user_id),
                        ),
                    ]
                ),
            )

            await db.commit()

        except Exception as exc:
            logger.exception("Semantic vector delete failed for user %s", user_id)
            raise RuntimeError("Semantic vector index delete failed") from exc