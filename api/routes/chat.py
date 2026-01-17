from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from api.dependencies import get_current_user
from db.models import Message, User, Thread
from services.message_service import create_message_by_api, create_or_update_message
from api.schemas.chat import ChatRequest, ChatResponse
from sqlalchemy.ext.asyncio import AsyncSession
from langchain_core.messages import HumanMessage, AIMessage
from langgraph.types import Command
from services.limiting import limiter
from core.database import get_db
from sqlalchemy import select
import asyncio
import json
import time
import logging
import traceback
from services.vector_db_faiss import FAISSVectorDB
from tools.user_tools_cache import get_user_allowed_tool_names  # For production error logging

logger = logging.getLogger(__name__)


router = APIRouter(prefix="/chat", tags=["Chat"])


@router.post("/stream")
@limiter.limit("5/minute;100/day")
async def chat_stream_endpoint(
    request: Request,
    req: ChatRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    vector_db: FAISSVectorDB = Depends(FAISSVectorDB.get_instance),
):
    try:
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
        await create_or_update_message(
            db=db,
            thread_id=str(req.thread_id),
            role="user",
            content=req.query,
            image_url=req.image_url,
            message_id=req.edit_message_id, # if value or none
            vector_db=vector_db,  # only used if rag_tool
        )

        chatbot = request.app.state.chatbot
        allowed_tool_names = await get_user_allowed_tool_names(user.id, db)
        tool_registry = request.app.state.tool_registry
        allowed_tools = tool_registry.get_by_names(allowed_tool_names)

        # Define config variable before loop
        config = {
            "configurable": {
                "thread_id": str(req.thread_id),
                "cookies": dict(request.cookies),
                "user_id": str(user.id),
                "llms": request.app.state.llms,
                "allowed_tools": allowed_tools,
                "tool_registry_version": tool_registry.version,
                "trace": {
                    "start_ts": time.perf_counter(),
                    "events": [],
                    "ui_events": [],
                },
            }
        }

        # Fetch current state to check for pauses
        state = await chatbot.aget_state(config)
        if state and state.interrupts and not req.query.strip():
            raise HTTPException(400, "Action required to continue")
        is_paused = bool(state.interrupts) if state else False


        # Input: always add message; let nodes handle parsing/updates
        if is_paused:
            # Always trust the graph
            interrupt = state.interrupts[-1]   # last interrupt
            hitl_reason = interrupt.value.get("type")

            input_payload = Command(resume={
                "messages": [HumanMessage(content=req.query)],
                "pending_confirmation": True,
                "hitl_reason": hitl_reason
            })
        else:
            input_payload = {
                "messages": [HumanMessage(content=req.query)],
                "thread_id": str(req.thread_id),
                "user_id": str(user.id),
            }


        async def event_generator(): 
            full_text = ""
            tool_calls_list = []
            interrupt_message = None
            interrupt_type = None
            interrupt_action = None
            interrupt_draft = None
            interrupt_reason = None
            interrupt_candidates = None
            was_interrupted = False
            final_emitted = False
            real_message_id = None
            trace = config["configurable"]["trace"]

            if req.edit_message_id:
                real_message_id = req.edit_message_id + 1
                yield f"data: {json.dumps({'type': 'message_created', 'message_id': real_message_id})}\n\n"
            else:
                # --- NEW: Create assistant message EARLY and send real ID ---
                try:
                    assistant_msg = await create_or_update_message(
                        db=db,
                        thread_id=str(req.thread_id),
                        role="assistant",
                        content="",
                        vector_db=vector_db,
                    )
                    real_message_id = assistant_msg.id

                    # Send real ID immediately so frontend can replace temp ID
                    yield f"data: {json.dumps({'type': 'message_created', 'message_id': real_message_id})}\n\n"

                except Exception as e:
                    logger.error(f"Failed to create assistant message early: {e}")
                    # Fallback: don't crash stream, but feedback won't work instantly
                    real_message_id = None

            try:
                async for event in chatbot.astream_events(
                    input_payload,
                    version="v2",
                    config=config,
                ):
                    
                    # 🔑 THIS is the important part
                    if event["event"] in ("on_llm_stream", "on_chat_model_stream"):
                        chunk = event["data"]["chunk"]
                        token = getattr(chunk, "content", None)
                        if token:
                            full_text += token
                            yield f"data: {json.dumps({'token': token})}\n\n"

                    if event["event"] == "on_chain_stream":
                        data = event.get("data") or {}
                        output = data.get("chunk") or {}
                        
                        # 🔒 HARD GATE: only dict outputs can contain interrupts
                        if not isinstance(output, dict):
                            continue

                        interrupts = output.get("__interrupt__")
                        if not interrupts:
                            continue

                        if interrupts:
                            was_interrupted = True
                            interrupt = interrupts[0]
                            payload = interrupt.value

                            if payload:
                                interrupt_type = payload.get("type")
                                interrupt_action = payload.get("action")
                                interrupt_draft = payload.get("draft") or {}  # Default to {} for safety
                                interrupt_message = payload.get("message") or "Awaiting user input..."  # Default message
                                interrupt_candidates = payload.get("candidates") or []  # Default to []
                                interrupt_reason = payload.get("reason") or "Human-in-the-loop required"

                                sse_payload = {
                                    "type": "interrupt",
                                    "interrupt_action": interrupt_action,
                                    "interrupt_type": interrupt_type,
                                    "draft": interrupt_draft,
                                    "message": interrupt_message,
                                    "reason": interrupt_reason,
                                    "candidates": interrupt_candidates,
                                }

                                # Send interrupt event to frontend
                                yield f"data: {json.dumps(sse_payload)}\n\n"

                    # Capture each tool call
                    if event["event"] == "on_tool_call":
                        tool_call_data = event["data"]
                        tool_calls_list.append({
                            "name": tool_call_data.get("name"),
                            "args": tool_call_data.get("args")
                        })

                    if event["event"] == "on_chain_end" and not final_emitted and not full_text:
                        output = event["data"].get("output")

                        if isinstance(output, dict):
                            messages = output.get("messages", [])
                            if messages and isinstance(messages[-1], AIMessage):
                                token = messages[-1].content or ""
                                if token:
                                    final_emitted = True
                                    full_text += token
                                    yield f"data: {json.dumps({'token': token})}\n\n"

                    await asyncio.sleep(0)

                if was_interrupted and not full_text.strip():
                    full_text = interrupt_message  # Use the interrupt summary as content

                # later when sending telemetry:
                if trace["ui_events"]:
                    yield f"data: {json.dumps({'type': 'telemetry', 'ui_events': trace['ui_events']})}\n\n"
                    trace["ui_events"].clear()

                yield "data: [DONE]\n\n"
                
            except Exception as exc:
                # Production-ready error handling: Log but don't expose stack
                logger.error(f"Stream error: {str(exc)}\n{traceback.format_exc()}")
                error_msg = "Sorry, an error occurred while processing your request. Please try again."
                full_text = error_msg  # NEW: Set full_text to error for saving
                yield f"data: {json.dumps({'error': error_msg})}\n\n"
                yield "data: [DONE]\n\n"

            # --- FINAL: Update the assistant message with full content ---
            if full_text.strip() and real_message_id:
                # Prepare metadata
                json_metadata = tool_calls_list[:] if tool_calls_list else None  # Shallow copy if list

                if was_interrupted:
                    if json_metadata is None or not isinstance(json_metadata, dict):
                        json_metadata = {}
                    else:
                        json_metadata = json_metadata.copy()
                    json_metadata["interrupt"] = True
                try:
                    await create_or_update_message(
                        db=db,
                        thread_id=str(req.thread_id),
                        role="assistant",
                        content=full_text,
                        json_metadata=json_metadata,
                        message_id=real_message_id,  # UPDATE existing!
                        vector_db=vector_db,
                    )
                except Exception as e:
                    logger.error(f"Failed to update assistant message {real_message_id}: {e}")

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
            },
        )
    
    except HTTPException as he:
        raise he
    except Exception as exc:
        logger.error(f"Endpoint error: {str(exc)}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail="Internal server error. Please try again later.")
    

async def fetch_messages_by_thread(db: AsyncSession, thread_id: str):
    """
    Returns a list of previous messages for a thread in chronological order.
    """
    result = await db.execute(
        select(Message).where(Message.thread_id == thread_id).order_by(Message.created_at.asc())
    )
    return result.scalars().all()



def extract_interrupt(final_state):
    """
    Safely extract interrupt payload from a LangGraph StateSnapshot
    """
    if final_state is None:
        return None

    # StateSnapshot → dict
    state = getattr(final_state, "values", None)
    if not isinstance(state, dict):
        return None

    interrupts = state.get("__interrupt__")
    if not interrupts:
        return None

    interrupt = interrupts[0]
    payload = getattr(interrupt, "value", None)

    if not isinstance(payload, dict):
        return None

    return {
        "type": payload.get("type"),
        "draft": payload.get("draft"),
        "message": payload.get("message"),
        "reason": payload.get("reason"),
        "candidates": payload.get("candidates"),
    }


@router.post("/stream_without_event")
async def chat_stream_endpoint(
    req: ChatRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        # ------------------------------------------------------------------
        # 1. Validate thread ownership
        # ------------------------------------------------------------------
        result = await db.execute(
            select(Thread).where(
                Thread.id == str(req.thread_id),
                Thread.user_id == user.id
            )
        )
        thread = result.scalar_one_or_none()
        if not thread:
            raise HTTPException(404, "Thread not found")

        # ------------------------------------------------------------------
        # 2. Persist user message immediately
        # ------------------------------------------------------------------
        await create_message_by_api(
            request=request,
            thread_id=str(req.thread_id),
            role="user",
            content=req.query,
        )

        chatbot = request.app.state.chatbot

        config = {
            "configurable": {
                "thread_id": str(req.thread_id),
                "user_id": user.id,
                "cookies": dict(request.cookies),
            }
        }

        # ------------------------------------------------------------------
        # 3. Detect paused graph (interrupt resume)
        # ------------------------------------------------------------------
        state = await chatbot.aget_state(config)
        is_paused = bool(state.interrupts)

        if is_paused:
            input_payload = Command(
                resume={
                    "messages": [HumanMessage(content=req.query)],
                    "expense_confirmed": True,
                    "pending_confirmation": True,
                }
            )
        else:
            input_payload = {
                "messages": [HumanMessage(content=req.query)],
                "thread_id": str(req.thread_id),
                "user_id": user.id,
            }

        # ------------------------------------------------------------------
        # 4. Streaming generator (pure token streaming)
        # ------------------------------------------------------------------
        async def event_generator():
            full_text = ""
            tool_calls = []

            try:
                async for msg in chatbot.astream(
                    input_payload,
                    config=config,
                ):
                    if isinstance(msg, AIMessage):
                        token = msg.content
                        if token:
                            full_text += token
                            yield f"data: {json.dumps({'token': token})}\n\n"

                    # Capture tool calls (optional metadata)
                    if hasattr(msg, "tool_calls") and msg.tool_calls:
                        for tc in msg.tool_calls:
                            tool_calls.append({
                                "name": tc.get("name"),
                                "args": tc.get("args"),
                            })

                    await asyncio.sleep(0)

                # ------------------------------------------------------------------
                # 5. POST-STREAM: inspect final graph state (interrupts)
                # ------------------------------------------------------------------
                final_state = await chatbot.aget_state(config)
                interrupt_payload = extract_interrupt(final_state)

                if interrupt_payload:
                    message = interrupt_payload.get("message") or ""
                    full_text += message

                    payload = {
                        "type": "interrupt",
                        **interrupt_payload
                    }

                    yield f"data: {json.dumps(payload)}\n\n"

                # ------------------------------------------------------------------
                # 6. Persist assistant message
                # ------------------------------------------------------------------
                await create_message_by_api(
                    request=request,
                    thread_id=str(req.thread_id),
                    role="assistant",
                    content=full_text,
                    json_metadata=tool_calls or None,
                    tool_call=[t["name"] for t in tool_calls] if tool_calls else None,
                )

                yield "data: [DONE]\n\n"

            except Exception as exc:
                logger.error(
                    f"Streaming error: {exc}\n{traceback.format_exc()}"
                )
                yield f"data: {json.dumps({'error': 'Unexpected error occurred'})}\n\n"
                yield "data: [DONE]\n\n"

        # ------------------------------------------------------------------
        # 7. Return SSE response
        # ------------------------------------------------------------------
        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
            },
        )

    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Endpoint failure: {exc}\n{traceback.format_exc()}")
        raise HTTPException(500, "Internal server error")



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
