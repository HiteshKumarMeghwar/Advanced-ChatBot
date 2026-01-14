# graphs/memory_extract.py
import logging
import time
from typing import List, Dict

from langchain_core.messages import BaseMessage
from pydantic import BaseModel, Field

from langmem import create_memory_manager

from services.pii_crypto import encrypt_fact, detect_pii_type
from services.memory_metrics import (
    MEMORY_EXTRACTION_TOTAL,
    MEMORY_EXTRACTION_FAILURES,
    MEMORY_EXTRACTED_TOTAL,
    PII_ENCRYPTED_TOTAL,
    MEMORY_EXTRACTION_LATENCY,
    SEMANTIC_SAVE_TOTAL,
)
from core.config import CONFIDENCE_THRESHOLD
from graphs.state import ChatState
from services.redis import push_episodic_turn
from services.semantic_memory import save_semantic_fact
from services.procedural_memory import save_rules

logger = logging.getLogger(__name__)

# --------------------- Separate Schemas for Each Memory Type ---------------------

class EpisodicMemory(BaseModel):
    """A short, chronological event or verbatim exchange that happened."""
    role: str = Field(..., description="user or assistant")
    content: str = Field(..., description="Verbatim short message or key event summary")
    confidence: float = Field(..., ge=0.0, le=1.0)

class SemanticMemory(BaseModel):
    """A durable fact about the user that remains true over time."""
    fact: str = Field(..., description="Long-term fact, preference, or trait about the user")
    confidence: float = Field(..., ge=0.0, le=1.0)

class ProceduralMemory(BaseModel):
    """A rule or instruction the assistant must follow in future responses."""
    rule: str = Field(..., description="Behavioral rule like 'Always respond in bullet points'")
    confidence: float = Field(..., ge=0.0, le=1.0)

class MemoryExtraction(BaseModel):
    """Structured extraction of memories from conversation, categorized into episodic, semantic, and procedural types.
    Use this to output exactly one JSON object with lists for each memory category."""
    episodic: list[EpisodicMemory] = Field(default=[], max_items=5)
    semantic: list[SemanticMemory] = Field(default=[], max_items=3)
    procedural: list[ProceduralMemory] = Field(default=[], max_items=2)

# Global manager – lazy initialized
_memory_manager = None


async def get_memory_manager(config):
    """Create and cache the LangMem manager with three separate schemas."""
    global _memory_manager
    llms = config.get("configurable", {}).get("llms")
    if _memory_manager is None:

        llm = llms["system"].with_structured_output(MemoryExtraction)

        _memory_manager = create_memory_manager(
            llm, # ← Correct: positional model argument
            schemas=[MemoryExtraction],
            instructions="""
            You are a highly conservative memory extraction system. Your ONLY job is to identify and extract durable, explicitly stated personal facts, preferences, or behavioral rules about the USER.

            STRICT RULES — FOLLOW EXACTLY:
            - Extract ONLY information explicitly stated by the user in the conversation.
            - NEVER extract general knowledge, facts about celebrities, historical events, or third parties unless the user explicitly says "Remember that [fact] about me".
            - NEVER extract anything that could be inferred — only direct statements.
            - Examples of valid semantic memories:
            ✓ "My favorite singer is Sidhu Moose Wala" → extract
            ✗ "Sidhu Moose Wala passed away in 2022" → DO NOT extract (general knowledge)
            ✗ "User seems sad about Sidhu Moose Wala" → DO NOT extract (inference)
            - For procedural: only extract if user says "Always do X" or "From now on, do Y".
            - If nothing meets the strict criteria with high confidence (>0.8), return empty lists.
            - Output exactly ONE clean JSON object. No repetition. No extra text.
            - Keep lists short: maximum 3 items per category unless explicitly repeated.
            - Prefer higher confidence for direct quotes.
            """,
            enable_inserts=True,   # ← Required: set to True to satisfy TrustCall
            enable_updates=False,
            enable_deletes=False,
        )
    return _memory_manager



async def extract_memory(
    user_id: int, 
    thread_id: str,
    all_messages: list,
    config
):
    """
    POST-LLM memory extraction using LangMem with a single wrapper schema.
    Deterministic, non-tool, production-safe.
    """

    MEMORY_EXTRACTION_TOTAL.inc()
    start = time.perf_counter()

    window: List[BaseMessage] = [
        m for m in all_messages[-6:]
        if hasattr(m, "content") and str(m.content).strip()
    ]

    if not window:
        logger.info("No messages for memory extraction")
        return

    try:
        manager = await get_memory_manager(config)

        conversation: List[Dict[str, str]] = [
            {"role": m.type, "content": str(m.content)}
            for m in window
        ]

        extracted = await manager.ainvoke(
            {"messages": conversation},
            config=config,
        )

        if not extracted:
            logger.info("LangMem returned no extraction object")
            return

        # ✅ SINGLE WRAPPER OBJECT
        result = extracted[0].content

        if not result:
            logger.info("LangMem extraction empty")
            return
        
        if not isinstance(result, MemoryExtraction):
            logger.warning("Invalid extraction type from LangMem")
            return

        procedural_rules: List[dict] = []

        # ---------------- EPISODIC ----------------
        for mem in result.episodic:
            if mem.confidence < CONFIDENCE_THRESHOLD:
                continue
            try:
                await push_episodic_turn(
                    user_id=user_id,
                    thread_id=thread_id,
                    role=mem.role,
                    content=mem.content.strip()[:500],
                )
                MEMORY_EXTRACTED_TOTAL.labels(type="episodic").inc()
                logger.info(f"Saved episodic: {mem.content[:60]}...")
            except Exception as e:
                logger.warning(f"Episodic save failed: {e}")

        # ---------------- SEMANTIC ----------------
        for mem in result.semantic:
            if mem.confidence < CONFIDENCE_THRESHOLD:
                continue

            fact_text = mem.fact.strip()
            encrypted = False

            pii_type = detect_pii_type(fact_text)
            if pii_type:
                fact_text = encrypt_fact(fact_text)
                encrypted = True
                PII_ENCRYPTED_TOTAL.labels(type=pii_type).inc()

            try:
                await save_semantic_fact(
                    user_id=user_id,
                    fact=fact_text,
                    confidence=mem.confidence,
                )
                MEMORY_EXTRACTED_TOTAL.labels(type="semantic").inc()
                SEMANTIC_SAVE_TOTAL.labels(
                    encrypted=str(encrypted).lower()
                ).inc()
                logger.info(
                    "Saved semantic memory (encrypted=%s, confidence=%.2f)",
                    encrypted,
                    mem.confidence,
                )
            except Exception as e:
                logger.warning(f"Semantic save failed: {e}")


        # ---------------- PROCEDURAL ----------------
        for mem in result.procedural:
            if mem.confidence < CONFIDENCE_THRESHOLD:
                continue

            rule_text = mem.rule.strip()[:200]
            if len(mem.rule) > 200:
                logger.warning("Procedural rule truncated (>200 chars)")

            procedural_rules.append({
                "rule": rule_text,
                "confidence": mem.confidence,
            })

        if procedural_rules:
            try:
                await save_rules(user_id, procedural_rules)
                MEMORY_EXTRACTED_TOTAL.labels(type="procedural").inc()
                logger.info(f"Saved {len(procedural_rules)} procedural rules")
            except Exception as e:
                logger.warning(f"Procedural save failed: {e}")

    except Exception as e:
        logger.exception(f"Memory extraction failed: {e}")
        MEMORY_EXTRACTION_FAILURES.inc()

    MEMORY_EXTRACTION_LATENCY.observe(time.perf_counter() - start)

    return
