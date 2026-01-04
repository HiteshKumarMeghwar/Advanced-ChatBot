import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select, delete, func, and_
from core.config import (
    MEMORY_MAINTENANCE_INTERVAL_SECONDS,
    SEMANTIC_DECAY_DAYS,        # global fallback
    SEMANTIC_DECAY_BATCH,
)
from db.database import AsyncSessionLocal
from db.models import SemanticMemory, UserMemorySetting
from services.vector_db_faiss import FAISSVectorDB

logger = logging.getLogger(__name__)
VS = FAISSVectorDB.get_instance()


# ------------------------------------------------------------------
# 1.  Fetch retention for one user (global fallback)
# ------------------------------------------------------------------
async def _retention_days_for(user_id: int) -> int:
    async with AsyncSessionLocal() as db:
        row = await db.scalar(select(UserMemorySetting.semantic_retention_days).filter_by(user_id=user_id))
    return row if row is not None else SEMANTIC_DECAY_DAYS


# ------------------------------------------------------------------
# 2.  Decay **per user** using retention_until (or calculated)
# ------------------------------------------------------------------
async def decay_semantic_memory_once(batch_size: int = SEMANTIC_DECAY_BATCH) -> int:
    async with AsyncSessionLocal() as db:
        # ---- oldest users with expired facts ----
        stmt = (
            select(SemanticMemory.user_id)
            .join(UserMemorySetting, SemanticMemory.user_id == UserMemorySetting.user_id)  
            .where(
                # retention_until < now  OR  (created_at + retention_days) < now
                func.coalesce(
                    SemanticMemory.retention_until,
                    SemanticMemory.created_at
                    + func.coalesce(
                        UserMemorySetting.semantic_retention_days, SEMANTIC_DECAY_DAYS
                    )
                    * timedelta(days=1)
                )
                < datetime.now(timezone.utc)
            )
            .distinct()
            .limit(50)  # max users per cron tick
        )
        user_ids = (await db.execute(stmt)).scalars().all()
        total = 0

        for uid in user_ids:
            retention_days = await _retention_days_for(uid)
            cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)

            # ---- fetch stale facts for this user ----
            facts_stmt = (
                select(SemanticMemory)
                .where(
                    SemanticMemory.user_id == uid,
                    # prefer retention_until if present
                    func.coalesce(SemanticMemory.retention_until, SemanticMemory.created_at + timedelta(days=retention_days))
                    < datetime.now(timezone.utc),
                )
                .order_by(SemanticMemory.created_at)
                .limit(batch_size)
            )
            rows = (await db.execute(facts_stmt)).scalars().all()
            if not rows:
                continue

            embedding_ids = [r.embedding_id for r in rows]

            # ---- atomic delete ----
            await db.execute(
                delete(SemanticMemory).where(
                    SemanticMemory.user_id == uid,
                    SemanticMemory.embedding_id.in_(embedding_ids),
                )
            )
            await db.commit()  # savepoint per user → idempotent

            # ---- idempotent FAISS rebuild (safe to re-run) ----
            try:
                await VS.delete_semantic_embeddings(user_id=uid, embedding_ids=embedding_ids, db=db)
                logger.info("Decayed %d semantic facts for user %s", len(rows), uid)
                total += len(rows)
            except Exception as e:
                logger.exception("FAISS rebuild failed for user %s: %s", uid, e)
                # continue with next user – job remains idempotent
    return total

async def memory_maintenance_loop(app_state):
    """
    app_state: container to signal graceful shutdown
    """
    logger.info("Memory maintenance loop starting")
    while not getattr(app_state, "shutdown", False):
        try:
            deleted_count = await decay_semantic_memory_once()
            if deleted_count:
                logger.info("Memory maintenance: removed %d semantic entries", deleted_count)
        except Exception:
            logger.exception("Memory maintenance run failed")

        await asyncio.sleep(MEMORY_MAINTENANCE_INTERVAL_SECONDS)

async def start_background_maintenance(app):
    # create a simple object to signal stop
    app.state.memory_maintenance_shutdown = False
    app.state.memory_maintenance_task = asyncio.create_task(memory_maintenance_loop(app.state))
    logger.info("Memory maintenance scheduled")
