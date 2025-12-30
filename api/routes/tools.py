from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from api.dependencies import get_current_user
from core.config import USAGE_LIMIT
from core.database import get_db
from db.models import Tool, User, UserTool
from sqlalchemy import delete, select
from tools.gather_tools import gather_tools
from tools.multiserver_mcpclient_tools import multiserver_mcpclient_tools

router = APIRouter(prefix="/tools", tags=["Tools"])


@router.post("/insert_all", summary="Insert all available tools into DB")
async def insert_all_tools(db: AsyncSession = Depends(get_db)):
    """
    Gather all tools from the code and insert them into the `tools` table.
    Skips tools that already exist (based on `name`).
    """
    tools_list =  await gather_tools()
    inserted_tools = []

    for t in tools_list:
        # Get a readable tool name
        name = getattr(t, "name", None) or t.__name__
        description = getattr(t, "description", "") or ""

        # Skip if already exists
        existing = (
            await db.execute(
                select(Tool)
                .where(Tool.name == name)
            )
        ).scalar_one_or_none()
        if existing:
            continue

        new_tool = Tool(name=name, description=description, status="active")
        db.add(new_tool)
        inserted_tools.append(name)

    await db.commit()

    if not inserted_tools:
        return {"message": "All tools already exist in DB."}

    return {"message": f"Inserted {len(inserted_tools)} new tools.", "tools": inserted_tools}