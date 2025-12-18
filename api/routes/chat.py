from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from api.dependencies import get_current_user
from db.models import User, Thread
from services.message_service import create_message_by_api
from api.schemas.chat import ChatRequest, ChatResponse
from sqlalchemy.ext.asyncio import AsyncSession
from langchain_core.messages import HumanMessage
from core.database import get_db
from sqlalchemy import select
import asyncio
import json


router = APIRouter(prefix="/chat", tags=["Chat"])


@router.post("/stream")
async def chat_stream_endpoint(
    req: ChatRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # 1. Validate thread
    result = await db.execute(
        select(Thread).where(
            Thread.id == str(req.thread_id),
            Thread.user_id == user.id
        )
    )
    thread = result.scalar_one_or_none()
    if not thread:
        raise HTTPException(404, "Thread not found")

    # 2. Save user message immediately
    await create_message_by_api(
        request=request,
        thread_id=str(req.thread_id),
        role="user",
        content=req.query,
    )

    chatbot = request.app.state.chatbot

    async def event_generator():
        full_text = ""

        async for event in chatbot.astream_events(
            {"messages": [HumanMessage(content=req.query)]},
            version="v1",
            config={
                "configurable": {
                    "thread_id": str(req.thread_id),
                    "request": request,
                }
            },
        ):
            print(event["event"])
            # 🔑 THIS is the important part
            if event["event"] in ("on_llm_stream", "on_chat_model_stream"):
                chunk = event["data"]["chunk"]
                token = getattr(chunk, "content", None)
                if token:
                    full_text += token
                    yield f"data: {json.dumps({'token': token})}\n\n"

            await asyncio.sleep(0)

        # 3. Save FINAL assistant message
        await create_message_by_api(
            request=request,
            thread_id=str(req.thread_id),
            role="assistant",
            content=full_text,
        )

        yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )



@router.post("/send", response_model=ChatResponse)
async def chat_endpoint(
    req: ChatRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    
    # Validate thread
    thread = await db.execute(
        select(Thread).where(
            Thread.id == str(req.thread_id),
            Thread.user_id == user.id
        )
    )
    thread = thread.scalar_one_or_none()
    if not thread:
        raise HTTPException(404, "Thread not found")

    # 1. Save user message (direct, no HTTP!)
    await create_message_by_api(
        request=request,
        thread_id=str(req.thread_id),
        role="user",
        content=req.query,
        json_metadata=None,
        tool_call=None
    )

    # 2. Get chatbot from app state
    chatbot = getattr(request.app.state, "chatbot", None)
    if chatbot is None:
        # Don't expose internals — give a helpful 503
        raise HTTPException(status_code=503, detail="Chat service not yet initialized")
    
    # Provide the thread_id in the config so chat_node can read it
    final_state = await chatbot.ainvoke(
        {"messages":[HumanMessage(content=req.query)]}, 
        config={
            "configurable": {
                "thread_id": str(req.thread_id),
                "request": request,
            }
        }
    )

    # ---- extract what we need ---------------------------------------------------
    last_msg   = final_state["messages"][-1]          # AIMessage
    content    = last_msg.content

    # ---- extract tool_call from final_state -------------------------------
    tool_name, tool_args = extract_tool_call(final_state)


    # ---- persist assistant reply ----------------------------------------------
    saved = await create_message_by_api(
        request=request,
        thread_id=str(req.thread_id),
        role="assistant",
        content=content,
        json_metadata=tool_args,
        tool_call=tool_name
    )

    # ---- response to client ----------------------------------------------------
    return ChatResponse(
        role="assistant",
        content=content,
        message_id=saved.id,                  
        thread_id=str(req.thread_id)
    )



def extract_tool_call(final_state):
    tool_name = None
    tool_args = None

    for msg in final_state["messages"]:
        if hasattr(msg, "tool_calls") and msg.tool_calls:
            # Only pick actual function tools
            call = msg.tool_calls[0]
            tool_name = call["name"]
            tool_args = call.get("args")
            break

    return tool_name, tool_args
