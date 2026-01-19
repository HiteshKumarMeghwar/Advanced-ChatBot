# services/semantic_memory.py
import uuid
import hashlib
from typing import List, Optional
from core.config import RAG_TOP_K, SEMANTIC_DECAY_DAYS, SEMANTIC_DEDUP_SIM_THRESHOLD, CONFIDENCE_THRESHOLD
from services.user_memory_settings_and_defaults import get_user_memory_settings_or_default
# from services.vector_db_faiss import FAISSVectorDB
from services.vector_db_qdrant import QdrantVectorDB
from db.database import AsyncSessionLocal
from db.models import SemanticMemory, UserMemorySetting
from langchain_core.documents import Document
import logging
from sqlalchemy import select, and_
from datetime import datetime, timedelta, timezone
from services.pii_crypto import decrypt_fact, detect_pii_type
from cryptography.fernet import InvalidToken
from services.memory_metrics import SEMANTIC_VERSIONED_TOTAL


logger = logging.getLogger(__name__)
VS = QdrantVectorDB.get_instance()

def fingerprint_text(text: str) -> str:
    norm = " ".join(text.lower().strip().split())
    h = hashlib.blake2b(norm.encode("utf-8"), digest_size=12).hexdigest()
    return f"fp_{h}"

async def find_nearest_duplicate(user_id: int, fact: str):
    hits = await VS.query(
        user_id=user_id,
        query=fact,
        top_k=1,
    )
    return hits[0] if hits else None

async def save_semantic_fact(user_id: int, fact: str, confidence: float = 0.95):
    """
    Save semantic fact only if user allows and dedup passes.
    Returns: dict with status and saved row id or reason.
    """
    settings = await get_user_memory_settings_or_default(user_id)
    if not settings["allow_semantic"]:
        logger.info("User %s disallowed semantic saves", user_id)
        return {"ok": False, "reason": "user_disabled"}

    fact_clean = fact.strip()
    if not fact_clean:
        return {"ok": False, "reason": "empty"}
    
    if confidence < CONFIDENCE_THRESHOLD:
        return

    fp = fingerprint_text(fact_clean)

    async with AsyncSessionLocal() as db:
        retention_days = await db.scalar(
            select(UserMemorySetting.semantic_retention_days).filter_by(user_id=user_id)
        )
    retention_days = retention_days or SEMANTIC_DECAY_DAYS
    retention_until = datetime.now(timezone.utc) + timedelta(days=retention_days)

    # 🔁 Semantic versioning:
    # If a similar semantic exists, expire it instead of hard-rejecting
    versioned = False
    async with AsyncSessionLocal() as db:
        existing = await db.execute(
            select(SemanticMemory)
            .where(SemanticMemory.user_id == user_id)
            .where(SemanticMemory.retention_until > datetime.now(timezone.utc))
        )
        for row in existing.scalars():
            if row.fingerprint == fp:
                # expire old version
                row.retention_until = datetime.now(timezone.utc)
                versioned = True
                logger.info(
                    "Expired previous semantic version for user %s (id=%s)",
                    user_id,
                    row.id,
                )
        await db.commit()
    if versioned:
        SEMANTIC_VERSIONED_TOTAL.inc()

    # 2) Vector similarity check (best-effort)
    nearest = await find_nearest_duplicate(user_id, fact_clean)
    if nearest:
        # if hit has score indicating high similarity -> duplicate
        score = float(nearest.get("score", 0.0))
        # if your VS returns distances, invert the check; adjust threshold accordingly.
        if score >= SEMANTIC_DEDUP_SIM_THRESHOLD:   # cosine similarity 0..1 (higher = more similar)
            logger.info("Duplicate semantic found by vector similarity for user %s (score=%.3f)", user_id, score)
            return {"ok": False, "reason": "duplicate_vector", "score": score}

    embedding_id = str(uuid.uuid4())

    # 3) Persist to DB first
    async with AsyncSessionLocal() as db:
        mem = SemanticMemory(
            user_id=user_id, 
            fact=fact_clean, 
            embedding_id=embedding_id, 
            fingerprint=fp, 
            confidence=confidence,
            retention_until=retention_until,
        )
        db.add(mem)
        await db.commit()
        await db.refresh(mem)
        saved_id = mem.id

    index_suffix = "_pii" if detect_pii_type(fact_clean) else ""

    doc = Document(
        page_content=fact_clean,
        metadata={
            "user_id": user_id,
            "embedding_id": embedding_id,
            "saved_semantic_id": saved_id,
            "pii": bool(index_suffix),
            "fingerprint": fp,
            "confidence": confidence,
            "retention_until": retention_until.timestamp(),
        },
    )

    try:
        await VS.add_semantic_documents(user_id, [doc], db=AsyncSessionLocal())
    except Exception as e:
        logger.error("Failed to add semantic vector for user %s: %s", user_id, e)
        # NOT raising: semantic fact persisted in MySQL — vector is optional
        return {"ok": True, "id": saved_id, "warning": "faiss_failed"}

    return {"ok": True, "id": saved_id}


async def query_semantic_facts(user_id: int, query: str, top_k: int = 1) -> List[str]:
    now = datetime.now(timezone.utc)

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(
                SemanticMemory.embedding_id,
                SemanticMemory.fact,
                SemanticMemory.fingerprint,
            ).where(
                and_(
                    SemanticMemory.user_id == user_id,
                    SemanticMemory.retention_until > now,
                )
            )
        )
        rows = result.all()

    active_embeddings = {r.embedding_id for r in rows}
    fingerprint_map = {r.embedding_id: r.fingerprint for r in rows}
    fact_map = {r.embedding_id: r.fact for r in rows}

    hits = await VS.query(
        user_id=user_id,
        query=query,
        top_k=top_k,
        pii=None,
    )

    results: List[str] = []

    for h in hits:
        embedding_id = h.get("metadata", {}).get("embedding_id")
        if embedding_id not in active_embeddings:
            # fallback: fingerprint match (thread-agnostic)
            hit_text = h.get("content") or h.get("page_content")
            if not hit_text:
                continue

            hit_fp = fingerprint_text(hit_text)
            matched = next(
                (eid for eid, fp in fingerprint_map.items() if fp == hit_fp),
                None
            )
            if not matched:
                continue

            embedding_id = matched

        content = fact_map.get(embedding_id)
        if not content:
            continue

        try:
            results.append(decrypt_fact(content))
        except InvalidToken:
            results.append(content)
        except Exception:
            logger.exception("Semantic decrypt failed for user %s", user_id)
            results.append(content)

    return results
