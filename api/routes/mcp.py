from fastapi import APIRouter, Depends, FastAPI, HTTPException, Body, Query, Request
from typing import Dict, List
import httpx
from bs4 import BeautifulSoup

from sqlalchemy import delete, select
from api.dependencies import get_current_user
from api.schemas.mcp import MCPServerConfig
from langchain_mcp_adapters.client import MultiServerMCPClient
from sqlalchemy.ext.asyncio import AsyncSession
from core.config import USAGE_LIMIT
from core.database import get_db
from db.models import MCPServer, MCPServerUserTool, Tool, User, UserTool
from langchain_core.tools import BaseTool
from services.mcp_registry import (
    load_mcp_servers,
    add_mcp_server,
    delete_mcp_server,
    mcp_server_by_name,
    reload_mcp_servers,
)
from tools.gather_tools import gather_tools
from tools.multiserver_mcpclient_tools import multiserver_mcpclient_tools

router = APIRouter(prefix="/mcp_server", tags=["MCP"])


@router.get("/health")
async def mcp_health(user: User = Depends(get_current_user)):
    try:
        servers = load_mcp_servers()
        return {
            "status": "ok",
            "servers_count": len(servers),
            "servers": list(servers.keys())
        }
    except Exception as exc:
        raise HTTPException(500, f"MCP health check failed: {exc}")


@router.post("/reload")
async def reload_servers(user: User = Depends(get_current_user)):
    servers = reload_mcp_servers()
    return {"status": "reloaded", "count": len(servers)}


@router.get("/show_all")
async def list_mcp_servers(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    rows = (
        await db.execute(
            select(MCPServer).where(MCPServer.owner_id == user.id)
        )
    ).scalars().all()

    return [
        {
            "id": r.id,
            "name": r.name,
            "transport": r.transport,
            "url": r.url,
            "created_at": r.created_at,
        }
        for r in rows
    ]
    
@router.post("/create", status_code=201)
async def create_mcp_server(
    request: Request,
    payload: MCPServerConfig,
    name: str = Body(..., embed=True),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    # 1️⃣ Prevent duplicates
    exists = (
        await db.execute(
            select(MCPServer)
            .where(MCPServer.owner_id == user.id)
            .where(MCPServer.name == name)
        )
    ).scalar_one_or_none()

    if exists:
        raise HTTPException(409, "MCP server already exists")

    # 2️⃣ Create MCP
    mcp = MCPServer(
        name=name,
        owner_id=user.id,
        **payload.model_dump(mode="json", exclude_unset=True),
    )
    db.add(mcp)
    await db.flush()  # get mcp.id

    # 4️⃣ Discover MCP tools
    try:
        client = MultiServerMCPClient(
            {name: payload.model_dump(mode="json", exclude_unset=True)}
        )
        mcp_tools = await client.get_tools()
    except Exception:
        raise HTTPException(400, "Failed to discover MCP tools")

    granted_tools: list[str] = []

    for t in mcp_tools:
        tool_name = getattr(t, "name", None)
        description = getattr(t, "description", "") or ""

        if not tool_name:
            continue

        # 5️⃣ Ensure Tool exists
        tool = (
            await db.execute(
                select(Tool).where(Tool.name == tool_name)
            )
        ).scalar_one_or_none()

        if not tool:
            tool = Tool(
                name=tool_name,
                description=description,
                scope="mcp",
                status="active",
            )
            db.add(tool)
            await db.flush()

        # 6️⃣ Ensure UserTool exists (USER ↔ TOOL)
        user_tool = (
            await db.execute(
                select(UserTool)
                .where(UserTool.user_id == user.id)
                .where(UserTool.tool_id == tool.id)
            )
        ).scalar_one_or_none()

        if not user_tool:
            user_tool = UserTool(
                user_id=user.id,
                tool_id=tool.id,
                usage_limit=USAGE_LIMIT,
                status="allowed",
            )
            db.add(user_tool)
            await db.flush()

        # 7️⃣ Link MCP ↔ UserTool (THIS IS THE POINT)
        link_exists = (
            await db.execute(
                select(MCPServerUserTool)
                .where(MCPServerUserTool.mcp_server_id == mcp.id)
                .where(MCPServerUserTool.user_tool_id == user_tool.id)
            )
        ).scalar_one_or_none()

        if not link_exists:
            db.add(
                MCPServerUserTool(
                    mcp_server_id=mcp.id,
                    user_tool_id=user_tool.id,
                )
            )
            granted_tools.append(tool_name)
            
    # 3️⃣ Runtime registry
    add_mcp_server(name, payload.model_dump(mode="json", exclude_unset=True))

    await db.commit()

    await refresh_tool_startup_without_rerun(request.app)

    return {
        "status": "created",
        "mcp": name,
        "mcp_id": mcp.id,
        "tools_granted": granted_tools,
        "tools_count": len(granted_tools),
    }



@router.delete("/delete_for_user")
async def delete_mcp_for_user(
    request: Request,
    mcp_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    mcp = (
        await db.execute(
            select(MCPServer)
            .where(MCPServer.id == mcp_id)
            .where(MCPServer.owner_id == user.id)
        )
    ).scalar_one_or_none()

    if not mcp:
        raise HTTPException(404, "MCP not found or not owned")

    # 2️⃣ Collect UserTool IDs EXPLICITLY (NO LAZY LOAD)
    result = await db.execute(
        select(MCPServerUserTool.user_tool_id)
        .where(MCPServerUserTool.mcp_server_id == mcp.id)
    )
    user_tool_ids = result.scalars().all()

    # 3️⃣ Delete MCP (bridge rows auto-deleted)
    await db.delete(mcp)
    await db.flush()

    # 4️⃣ Delete orphaned UserTools
    if user_tool_ids:
        await db.execute(
            delete(UserTool)
            .where(UserTool.id.in_(user_tool_ids))
            .where(~UserTool.mcp_links.any())
            .where(UserTool.tool.has(Tool.scope == "mcp"))
        )
    
    # remove runtime registry using NAME (internal detail)
    delete_mcp_server(mcp.name)
    await db.commit()
    await refresh_tool_startup_without_rerun(request.app)

    return {
        "status": "deleted",
        "mcp_id": mcp.id,
        "mcp": mcp.name,
        "revoked_tools_count": None,  # optional later
    }



@router.post("/backfill_mcp_tools", summary="Insert MCP tools and grant them to a user")
async def insert_tool_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    1. Discover MCP tools
    2. Insert missing tools into `tools`
    3. Grant those tools to the given user via `user_tools`
    """

    mcp_tools = await multiserver_mcpclient_tools()
    if not mcp_tools:
        raise HTTPException(status_code=400, detail="No MCP tools discovered")

    granted_tools = []

    for t in mcp_tools:
        name = getattr(t, "name", None) or t.__name__
        description = getattr(t, "description", "") or ""

        # 1️⃣ Ensure tool exists
        tool = (
            await db.execute(
                select(Tool).where(Tool.name == name)
            )
        ).scalar_one_or_none()

        if not tool:
            tool = Tool(
                name=name,
                description=description,
                status="active",
            )
            db.add(tool)
            await db.flush()  # get tool.id without commit

        # 2️⃣ Check bridge table
        exists = (
            await db.execute(
                select(UserTool)
                .where(UserTool.user_id == user.id)
                .where(UserTool.tool_id == tool.id)
            )
        ).scalar_one_or_none()

        if exists:
            continue

        # 3️⃣ Grant tool to user
        db.add(
            UserTool(
                user_id=user.id,
                tool_id=tool.id,
                usage_limit=USAGE_LIMIT,
                status="allowed",
            )
        )
        granted_tools.append(name)

    await db.commit()

    await refresh_tool_startup_without_rerun(request.app)

    return {
        "message": "MCP tools granted to user",
        "count": len(granted_tools),
        "tools": granted_tools,
    }


async def refresh_tool_startup_without_rerun(app: FastAPI):
    tools = await gather_tools()
    await app.state.tool_registry.refresh(tools)


MCP_BASE_URL = "https://mcpservers.org/servers"
@router.post("/search")
async def search_mcp_server(mcp_query: str = Query(..., alias="mcp_query")):
    """
    Search MCP servers from mcpservers.org based on query string.
    Returns JSON list of servers with name, url, description.
    """
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=10) as client:
            # Fetch the main servers page
            resp = await client.get(MCP_BASE_URL)
            resp.raise_for_status()
            html = resp.text

        # Parse HTML using BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")

        results = []
        # Find server entries (adjust selectors according to site's HTML)
        for server_div in soup.select("div.server-card"):  # example selector
            name = server_div.select_one("h3")  # adjust if needed
            url = server_div.select_one("a")
            desc = server_div.select_one("p.description")  # optional

            if not name or not url:
                continue

            name_text = name.get_text(strip=True)
            url_text = url.get("href")
            desc_text = desc.get_text(strip=True) if desc else ""

            # Filter based on query
            if mcp_query.lower() in name_text.lower():
                results.append({
                    "name": name_text,
                    "url": url_text,
                    "description": desc_text
                })

        return results

    except httpx.RequestError as e:
        raise HTTPException(status_code=502, detail=f"Failed to reach MCP upstream: {e}")
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=502, detail=f"MCP upstream returned error: {e.response.status_code}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {e}")