# core/llm_limits.py
import asyncio

BACKGROUND_LLM_SEMAPHORE = asyncio.Semaphore(1)
