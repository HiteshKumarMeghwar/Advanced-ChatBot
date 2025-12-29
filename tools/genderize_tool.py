from langchain_core.tools import tool
from langchain_core.runnables import RunnableConfig
from core.config import GENDERIZE_API, INTERNAL_TIMEOUT
import httpx


# Genderize tool ................
@tool
async def get_gender_of_given_name(user_name: str, config: RunnableConfig) -> dict:

    """Return gender and probability for a given first name."""

    cookies = (config.get("configurable") or {}).get("cookies") or {}

    base = GENDERIZE_API.rstrip()
    timeout = httpx.Timeout(INTERNAL_TIMEOUT)
    params = {"name": user_name}

    async with httpx.AsyncClient(timeout=timeout, cookies=cookies) as client:
        try:
            r = await client.get(base, params=params)
            r.raise_for_status()
            return r.json()
        except Exception as exc:
            return {"error": str(exc)}