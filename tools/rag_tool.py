import httpx
import logging
from langchain_core.tools import tool
from langchain_core.runnables import RunnableConfig
from core.config import INTERNAL_BASE_URL, INTERNAL_TIMEOUT, RAG_TOP_K

logger = logging.getLogger(__name__)

@tool
async def rag_tool(query: str, config: RunnableConfig) -> dict:
    """
    Retrieve relevant chunks from documents for this thread.
    Defensive: if thread_id missing/placeholder, log and return helpful diagnostic payload.
    """

    thread_id = config.get("configurable", {}).get("thread_id")

    base = INTERNAL_BASE_URL.rstrip("/")
    timeout = httpx.Timeout(INTERNAL_TIMEOUT)

    # Proceed with vector backend calls
    async with httpx.AsyncClient(timeout=timeout) as client:
        # 1. index exists?
        try:
            exists = await client.head(f"{base}/vector/exists_index/{thread_id}")
            if exists.status_code == 404:
                logger.info("No index for thread %s (exists returned 404)", thread_id)
                return {"query": query, "context": [], "metadata": [], "source_file": None}
        except httpx.HTTPError as exc:
            logger.exception("Error checking index exists for thread %s: %s", thread_id, exc)
            return {"query": query, "context": [], "metadata": [], "source_file": None}

        # 2. semantic search
        params = {"q": query, "top_k": RAG_TOP_K}
        try:
            resp = await client.get(
                f"{base}/vector/semantic_search/{thread_id}",
                params=params
            )
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            logger.exception("Semantic search failed for thread %s: %s", thread_id, exc)
            return {"query": query, "context": [], "metadata": [], "source_file": None}

    hits = resp.json()
    if not hits:
        return {"query": query, "context": [], "metadata": [], "source_file": None}

    context = [h["content"] for h in hits]
    metadata = [h["metadata"] for h in hits]
    source_file = metadata[0].get("source") if metadata else None
    return {"query": query, "context": context, "metadata": metadata, "source_file": source_file}