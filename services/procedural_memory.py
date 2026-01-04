# services/procedural_memory.py
import hashlib
from db.database import AsyncSessionLocal
from db.models import ProceduralMemory, UserMemorySetting
from datetime import datetime, timedelta, timezone
from sqlalchemy import select, delete
import json
import logging
logger = logging.getLogger(__name__)

# ------------------------------------------------------------------
# 1)  helpers
# ------------------------------------------------------------------
def _fingerprint(rule: str) -> str:
    """Blake2b hash of normalised rule (same as semantic)."""
    norm = " ".join(rule.lower().strip().split())
    h = hashlib.blake2b(norm.encode("utf-8"), digest_size=16).hexdigest()
    return f"fp_{h}"


async def user_allows_procedural(user_id: int) -> bool:
    async with AsyncSessionLocal() as db:
        row = await db.scalar(select(UserMemorySetting).filter_by(user_id=user_id))
        return row.allow_procedural if row else True

async def save_rules(user_id: int, rules: list[dict]):
    """
    rules: list of dicts {rule: "text", confidence: 0.9}
    Upsert each rule by fingerprint or add new.
    """

    if not await user_allows_procedural(user_id):
        logger.info("User %s disallowed procedural saves", user_id)
        return {"ok": False, "reason": "user_disabled"}

    if not rules:
        return

    async with AsyncSessionLocal() as db:
        for r in rules:
            text = r.get("rule") if isinstance(r, dict) else r
            conf = r.get("confidence", 1.0) if isinstance(r, dict) else 1.0
            fp = _fingerprint(text)
            # Simple dedup by exact text; you can fingerprint similarly to semantic
            existing = await db.scalar(select(ProceduralMemory).filter_by(user_id=user_id, fingerprint=fp))
            if existing:
                existing.confidence = max(existing.confidence or 0.0, conf)
                existing.updated_at = datetime.now(timezone.utc)
            else:
                # only ONE row per user (unique constraint on user_id) so that's why delete first
                await db.execute(
                    delete(ProceduralMemory).where(ProceduralMemory.user_id == user_id)
                )
                db.add(ProceduralMemory(user_id=user_id, rules=text, confidence=conf, fingerprint=fp))
        await db.commit()
    logger.info("Saved %d procedural rules for user %s", user_id)
    return {"ok": True}

async def get_rules(user_id: int) -> list[str]:
    async with AsyncSessionLocal() as db:
        rows = await db.execute(select(ProceduralMemory).filter_by(user_id=user_id, active=True))
        rules = [r.rule for r in rows.scalars().all()]
        return rules
