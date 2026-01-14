from langchain_core.tools import tool
from langchain_core.runnables import RunnableConfig
import httpx
from db.database import AsyncSessionLocal
from services.integration_helpers import get_integration_token
from core.database import get_db


@tool
async def twitter_profile_tool(config: RunnableConfig) -> dict:
    """
    Fetch Twitter/X profile for the connected account.
    """
    cfg = config or {}
    user_id = (cfg.get("configurable") or {}).get("user_id")

    async with AsyncSessionLocal() as db:
        token = await get_integration_token(db, user_id, "twitter")

    if not token:
        return {
            "status": "not_connected_or_disabled",
            "provider": "twitter",
            "data": [],
            "message": "Twitter account is not connected or disabled."
        }

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(
            "https://api.twitter.com/2/users/me",
            headers={"Authorization": f"Bearer {token}"}
        )

    if resp.status_code != 200:
        return {
            "status": "error",
            "provider": "twitter",
            "data": [],
            "message": "Failed to fetch Twitter profile."
        }

    return {
        "status": "ok",
        "provider": "twitter",
        "data": resp.json(),
        "message": "Twitter profile retrieved."
    }
