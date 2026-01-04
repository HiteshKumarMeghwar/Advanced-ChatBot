# services/message_service.py
from typing import List, Union
from fastapi import Request
import httpx
from core.config import INTERNAL_BASE_URL, INTERNAL_TIMEOUT
from db.models import Message
from datetime import datetime

async def create_message_by_api(
    *,
    request: Request,
    thread_id: str,
    role: str,
    content: str,
    image_url: str | None = None,
    json_metadata: dict | list | None = None,
    tool_call: Union[str, List[str], None] = None,
) -> Message:
    """
    Persist a message via internal HTTP call /messages/create
    so we keep a single source of truth (same validations, same RAG logic).
    """
    base   = INTERNAL_BASE_URL.rstrip("/")
    url    = f"{base}/messages/create"
    payload = {
        "thread_id": thread_id,
        "role": role,
        "content": content,
        "image_url": image_url,
        "json_metadata": json_metadata,
        "tool_call": tool_call,
    }

    timeout = httpx.Timeout(INTERNAL_TIMEOUT)
    async with httpx.AsyncClient(timeout=timeout, cookies=request.cookies) as client:
        try:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            # log and re-raise so caller can react
            raise RuntimeError(f"Failed to create message via API: {exc}") from exc

    # response body is MessageRead (same fields we need)
    data = resp.json()
    # convert to ORM instance if you need it; here we just return a dummy
    # with the keys we care about
    return Message(
        id=data["id"],
        thread_id=data["thread_id"],
        role=data["role"],
        content=data["content"],
        image_url=data["image_url"],
        json_metadata=data.get("json_metadata"),
        created_at=datetime.fromisoformat(data["created_at"]),
    )