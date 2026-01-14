from langchain_core.tools import tool
from langchain_core.runnables import RunnableConfig
import httpx
from db.database import AsyncSessionLocal
from services.integration_helpers import get_integration_token
from core.database import get_db


@tool
async def github_repos_tool(config: RunnableConfig) -> dict:
    """
    Fetch GitHub repositories for the connected account.
    """
    cfg = config or {}
    user_id = (cfg.get("configurable") or {}).get("user_id")

    async with AsyncSessionLocal() as db:
        token = await get_integration_token(db, user_id, "github")

    if not token:
        return {
            "status": "not_connected_or_disabled",
            "provider": "github",
            "data": [],
            "message": "GitHub account is not connected or disabled."
        }

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(
            "https://api.github.com/user/repos",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
            }
        )

    if resp.status_code != 200:
        return {
            "status": "error",
            "provider": "github",
            "data": [],
            "message": "Failed to fetch GitHub repositories."
        }

    return {
        "status": "ok",
        "provider": "github",
        "data": resp.json(),
        "message": "GitHub repositories fetched."
    }
