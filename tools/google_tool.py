from langchain_core.tools import tool
from langchain_core.runnables import RunnableConfig
import httpx
from db.database import AsyncSessionLocal
from services.integration_helpers import get_integration_token
from core.database import get_db

@tool
async def google_profile_tool(config: RunnableConfig) -> dict:
    """
    Fetch basic Google profile for the connected account.
    """
    cfg = config or {}
    user_id = (cfg.get("configurable") or {}).get("user_id")

    async with AsyncSessionLocal() as db:
        token = await get_integration_token(db, user_id, "google")

    if not token:
        return {
            "status": "not_connected_or_disabled",
            "provider": "google",
            "data": [],
            "message": "Google account is not connected or disabled."
        }

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(
            "https://www.googleapis.com/oauth2/v3/userinfo",
            headers={"Authorization": f"Bearer {token}"}
        )

    if resp.status_code != 200:
        return {
            "status": "error",
            "provider": "google",
            "data": [],
            "message": "Failed to fetch Google profile."
        }

    return {
        "status": "ok",
        "provider": "google",
        "data": resp.json(),
        "message": "Google profile retrieved."
    }
