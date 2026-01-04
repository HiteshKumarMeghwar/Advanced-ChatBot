from fastapi import APIRouter, Depends, FastAPI, HTTPException, Body, Request
from typing import Dict, List

from sqlalchemy import delete, select
from api.dependencies import get_current_user
from api.schemas.mcp import MCPServerConfig
from langchain_mcp_adapters.client import MultiServerMCPClient
from sqlalchemy.ext.asyncio import AsyncSession
from core.config import USAGE_LIMIT
from core.database import get_db
from db.models import Tool, User, UserTool
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


@router.get("/show_all", response_model=Dict)
async def list_mcp_servers(
    user: User = Depends(get_current_user),
):
    return load_mcp_servers()


@router.post("/create", status_code=201)
async def create_mcp_server(
    payload: MCPServerConfig = Body(...),
    name: str = Body(..., embed=True),
    user: User = Depends(get_current_user),
):
    try:
        config_dict = payload.model_dump(mode="json", exclude_unset=True)
        add_mcp_server(name, config_dict)
        return {"status": "created", "name": name}

    except ValueError as exc:
        raise HTTPException(409, str(exc))
    


@router.delete("/delete_for_user")
async def delete_mcp_for_user(
    request: Request,
    mcp_name: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):

    # 1. Get all MCP tools
    mcp_servers = mcp_server_by_name(mcp_name)

    if not mcp_servers:
        raise HTTPException(404, f"MCP server '{mcp_name}' not found")

    try:
        client = MultiServerMCPClient({mcp_name: mcp_servers})
        tools: List[BaseTool] = await client.get_tools()
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to load tools for MCP server '{mcp_name}'",
        )


    deleted_tools: list[str] = []

    for tool in tools:

        db_tool = (
            await db.execute(
                select(Tool).where(Tool.name == tool.name)
            )
        ).scalar_one_or_none()

        if not db_tool:
            continue

        await db.execute(
            delete(UserTool).where(
                UserTool.user_id == user.id,
                UserTool.tool_id == db_tool.id,
            )
        )
        deleted_tools.append(tool.name)

    # Remove MCP server from JSON
    delete_mcp_server(mcp_name)

    await refresh_tool_startup_without_rerun(request.app)

    await db.commit()

    return {
        "message": f"MCP server '{mcp_name}' removed successfully",
        "deleted_tools_count": len(deleted_tools),
        "deleted_tools": deleted_tools,
    }



@router.post("/insert_tool_user", summary="Insert MCP tools and grant them to a user")
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