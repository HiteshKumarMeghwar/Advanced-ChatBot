from sqlalchemy.ext.asyncio import AsyncSession
from db.models import Message, QueryProvenance
from services.vector_db_faiss import FAISSVectorDB
import json
from core.config import RAG_TOP_K

async def create_message_direct_async(
    *,
    db: AsyncSession,
    thread_id: str,
    role: str,
    content: str,
    json_metadata: dict | None = None,
    tool_call: str | None = None,
    vector_db: FAISSVectorDB | None = None,
) -> Message:
    """
    Async version of create_message_direct. Returns the ORM Message object (attached to session).
    """
    db_message = Message(
        thread_id=thread_id,
        role=role,
        content=content,
        json_metadata=json.dumps(json_metadata) if json_metadata is not None else None,
    )
    db.add(db_message)
    await db.flush()  # populate PK

    # RAG branch
    if tool_call == "rag_tool" and vector_db is not None:
        hits = await vector_db.query(thread_id=thread_id, query=content, top_k=RAG_TOP_K)
        # Save provenance rows
        for hit in hits:
            chunk_id = int(hit["metadata"]["chunk_id"])
            qp = QueryProvenance(message_id=db_message.id, chunk_id=chunk_id, score=hit["score"])
            db.add(qp)
        citations = [
            {
                "chunk_id": int(h["metadata"]["chunk_id"]),
                "document_id": int(h["metadata"].get("document_id", 0)),
                "score": float(h["score"]),
                "source": h["metadata"].get("source", ""),
            }
            for h in hits
        ]
        final_metadata = json_metadata or {}
        final_metadata["citations"] = citations
        db_message.json_metadata = json.dumps(final_metadata)

    await db.commit()
    await db.refresh(db_message)
    return db_message