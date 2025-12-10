from langchain_core.tools import tool
from core.config import GENDERIZE_API, INTERNAL_TIMEOUT
import httpx


# Genderize tool ................
@tool
async def get_gender_of_given_name(user_name: str) -> dict:

    """Return gender and probability for a given first name."""

    params = {"name": user_name}
    async with httpx.AsyncClient(timeout=INTERNAL_TIMEOUT) as client:
        try:
            r = await client.get(GENDERIZE_API.rstrip(), params=params)
            r.raise_for_status()
            return r.json()
        except Exception as exc:
            return {"error": str(exc)}