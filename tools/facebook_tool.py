from langchain_core.tools import tool
from langchain_core.runnables import RunnableConfig
import httpx
from db.database import AsyncSessionLocal
from services.integration_helpers import get_integration_token
from core.database import get_db


@tool
async def facebook_profile_tool(config: RunnableConfig) -> dict:
    """
    Fetch Facebook profile for the connected account.
    """
    cfg = config or {}
    user_id = (cfg.get("configurable") or {}).get("user_id")

    async with AsyncSessionLocal() as db:
        token = await get_integration_token(db, user_id, "facebook")

    if not token:
        return {
            "status": "not_connected_or_disabled",
            "provider": "facebook",
            "data": [],
            "message": "Facebook account is not connected or disabled."
        }

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(
            "https://graph.facebook.com/me",
            params={"fields": "id,name,email"},
            headers={"Authorization": f"Bearer {token}"}
        )

    if resp.status_code != 200:
        return {
            "status": "error",
            "provider": "facebook",
            "data": [],
            "message": "Failed to fetch Facebook profile."
        }

    return {
        "status": "ok",
        "provider": "facebook",
        "data": resp.json(),
        "message": "Facebook profile retrieved."
    }
