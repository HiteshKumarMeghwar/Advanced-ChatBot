# services/procedural_memory.py
import hashlib
from db.database import AsyncSessionLocal
from db.models import ProceduralMemory, UserMemorySetting
from datetime import datetime, timedelta, timezone
from sqlalchemy import func, select, delete
import json
import logging

from services.user_memory_settings_and_defaults import get_user_memory_settings_or_default
logger = logging.getLogger(__name__)

# ------------------------------------------------------------------
# 1)  helpers
# ------------------------------------------------------------------
def _fingerprint(rule: str) -> str:
    """Blake2b hash of normalised rule (same as semantic)."""
    norm = " ".join(rule.lower().strip().split())
    h = hashlib.blake2b(norm.encode("utf-8"), digest_size=16).hexdigest()
    return f"fp_{h}"

async def save_rules(user_id: int, rules: list[dict]):
    """
    rules: list of dicts {rule: "text", confidence: 0.9}
    Upsert each rule by fingerprint or add new.
    """
    settings = await get_user_memory_settings_or_default(user_id)
    if not settings["allow_procedural"]:
        logger.info("User %s disallowed procedural saves", user_id)
        return {"ok": False, "reason": "user_disabled"}

    if not rules:
        return {"ok": True}

    async with AsyncSessionLocal() as db:
        # fetch or create the single row
        row = await db.scalar(
            select(ProceduralMemory).filter_by(user_id=user_id).with_for_update()
        )
        if not row:
            row = ProceduralMemory(user_id=user_id, rules="[]", confidence=0.0, fingerprint="")
            db.add(row)

        # current list + conf
        existing_rules = _unpack_rules(row.rules)
        max_conf = row.confidence or 0.0

        # append / dedup
        for r in rules:
            text = r.get("rule") if isinstance(r, dict) else r
            conf = r.get("confidence", 1.0) if isinstance(r, dict) else 1.0
            if text not in existing_rules:
                existing_rules.append(text)
            max_conf = max(max_conf, conf)

        # save back
        row.rules = _pack_rules(existing_rules)
        row.confidence = max_conf
        row.fingerprint = _fingerprint(_pack_rules(existing_rules))  # cheap global hash
        row.updated_at = func.now()
        await db.commit()
    logger.info("Saved %d procedural rules for user %s", user_id)
    return {"ok": True}

async def get_rules(user_id: int) -> list[str]:
    async with AsyncSessionLocal() as db:
        row = await db.scalar(
            select(ProceduralMemory).filter_by(user_id=user_id, active=True)
        )
        return _unpack_rules(row.rules) if row else []


# ---------- helpers ----------
def _pack_rules(rules: list[str]) -> str:
    """Store list as JSON string."""
    return json.dumps(rules, ensure_ascii=False)

def _unpack_rules(raw: str | None) -> list[str]:
    """Load JSON string back to list."""
    if not raw:
        return []
    try:
        return json.loads(raw)
    except Exception:
        return []   # fallback for corrupted data