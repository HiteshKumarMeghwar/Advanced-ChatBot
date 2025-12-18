import os
import aiofiles.os
import logging
from typing import List, Optional, Dict
from pathlib import Path
import threading  
import asyncio     
from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document
import shutil
from sqlalchemy.ext.asyncio import AsyncSession as DBSession

from services.embeddings import EmbeddingsCreator
from db.models import EmbeddingMetadata
from core.config import FAISS_INDEXES_DIR, EMBEDDING_MODEL, RAG_TOP_K

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------
# production singleton
# ------------------------------------------------------------------
class FAISSVectorDB:
    _singleton: Optional["FAISSVectorDB"] = None
    _lock = threading.Lock()                     # NEW

    def __init__(
        self,
        embedding_model_name: str = EMBEDDING_MODEL,
        index_dir: str = FAISS_INDEXES_DIR,
        *,
        allow_dangerous_deserialization: bool = False,
    ):
        self.index_dir = Path(index_dir)
        self.index_dir.mkdir(exist_ok=True)

        self.embedder = EmbeddingsCreator(embedding_model_name).model
        self.allow_dangerous = allow_dangerous_deserialization


    @classmethod
    def get_instance(cls) -> "FAISSVectorDB":
        """Thread-safe singleton factory."""
        if cls._singleton is None:               # first check (no lock)
            with cls._lock:                      # second check (thread-safe)
                if cls._singleton is None:       # really still None?
                    cls._singleton = cls(
                        embedding_model_name=EMBEDDING_MODEL,
                        index_dir=FAISS_INDEXES_DIR,
                        allow_dangerous_deserialization=os.getenv("FAISS_ALLOW_DANGEROUS", "false").lower() == "true",
                    )
        return cls._singleton
    
    # ------------------------------------------------------------------
    # internals
    # ------------------------------------------------------------------
    def _index_path(self, thread_id: str) -> Path:
        return self.index_dir / f"faiss_{thread_id}"

    # ------------------------------------------------------------------
    # ASYNC add_documents
    # ------------------------------------------------------------------
    async def add_documents(
        self,
        thread_id: str,
        documents: List[Document],
        db: DBSession
        # metadatas: Optional[List[Dict]] = None,
    ) -> None:
        index_path = self._index_path(thread_id)

        # Heavy sync FAISS actions → Run in worker thread
        def _sync_faiss_op():
            if index_path.exists():
                vs = FAISS.load_local(
                    folder_path=str(index_path),
                    embeddings=self.embedder,
                    allow_dangerous_deserialization=self.allow_dangerous
                )
                vs.add_documents(documents)
            else:
                vs = FAISS.from_documents(
                    documents=documents,
                    embedding=self.embedder
                )
            vs.save_local(str(index_path))

        try:
            await asyncio.to_thread(_sync_faiss_op)

            # ---------- write EmbeddingMetadata ----------
            for doc in documents:
                vector_id = f"{thread_id}_{doc.metadata['document_id']}_{doc.metadata['chunk_index']}"
                db.add(
                    EmbeddingMetadata(
                        chunk_id=int(doc.metadata["chunk_id"]),  # must be in metadata
                        vector_id=vector_id,
                        embedding_model=EMBEDDING_MODEL,
                    )
                )
            await db.commit()

        except Exception as exc:
            logger.exception("Failed to add documents to thread %s", thread_id)
            raise RuntimeError("Vector index update failed") from exc

    async def query(self, thread_id: str, query: str, top_k: int = RAG_TOP_K) -> List[Dict]:
        index_path = self._index_path(thread_id)
        if not index_path.exists():
            return []
        
        def _sync_query():
            vs = FAISS.load_local(
                folder_path=str(index_path),
                embeddings=self.embedder,
                allow_dangerous_deserialization=self.allow_dangerous
            )
            return vs.similarity_search_with_score(query, k=top_k)

        try:
            docs_with_score = await asyncio.to_thread(_sync_query)

            return [
                {"content": doc.page_content, "metadata": doc.metadata, "score": float(score)}
                for doc, score in docs_with_score
            ]
        except Exception as exc:
            logger.warning("Query on thread %s failed: %s", thread_id, exc)
            return []   # graceful degradation

    async def delete_thread_index(self, thread_id: str) -> None:
        index_path = self._index_path(thread_id)
        if index_path.exists():
            await asyncio.to_thread(lambda: shutil.rmtree(index_path))
            logger.info("Deleted index for thread %s", thread_id)
            
    
    async def exists(self, thread_id: str) -> bool:
        return await aiofiles.os.path.exists(self._index_path(thread_id))
    

    async def rebuild_thread_index(
        self,
        thread_id: str,
        documents: list[Document],
    ) -> None:
        """
        Rebuild FAISS index for a thread using remaining documents.
        """
        index_path = self._index_path(thread_id)

        def _sync_rebuild():
            # remove old index completely
            if index_path.exists():
                shutil.rmtree(index_path)

            if not documents:
                return  # no docs left → no index

            vs = FAISS.from_documents(
                documents=documents,
                embedding=self.embedder
            )
            vs.save_local(str(index_path))

        await asyncio.to_thread(_sync_rebuild)
