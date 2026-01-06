# graphs/chat_graph.py
from langchain_core.messages import AIMessage, RemoveMessage
from langgraph.graph import StateGraph, START, END
from graphs.dynamic_prompt import render_system_prompt
from graphs.memory_extract_background import extract_memory_background
from graphs.memory_inject import inject_memory
from graphs.parent_graph import build_graph_parent
from graphs.state import ChatState
from core.config import HISTORY_SUMMARY_MEMORY_LIMIT, LLM_TIMEOUT
import logging
import asyncio
import time
import copy

logger = logging.getLogger(__name__)

# ------------------ CHATBOT INSTANCE ----------------------
groq_generator_llm = None
groq_llm_with_tools = None


# --------------------- CHAT NODE ------------------------------
async def meghx_node(state: ChatState, config=None):

    t0 = time.perf_counter()
    system_message = await render_system_prompt(state)
    msgs = [system_message, *state["messages"][-2:]]
    user_id = config.get("configurable", {}).get("user_id")
    llms = config.get("configurable", {}).get("llms")
    allowed_tools = config.get("configurable", {}).get("allowed_tools")
    trace = config.get("configurable", {}).get("trace")

    
    
    groq_generator_llm = llms["chat_base"]
    if allowed_tools:
        groq_llm_with_tools = groq_generator_llm.bind_tools(allowed_tools)
    else:
        groq_llm_with_tools = groq_generator_llm


    try:
        response = await asyncio.wait_for(groq_llm_with_tools.ainvoke(msgs, config=config), timeout=LLM_TIMEOUT)
    except asyncio.TimeoutError:
        logger.error("LLM call timed out")
        response = AIMessage(content="⚠️ Sorry, the assistant is temporarily unavailable.")
    except Exception as e:
        if "tool call validation failed" in str(e):
            logger.warning("Invalid tool call detected, falling back to chat LLM")
            response = await asyncio.wait_for(groq_generator_llm.ainvoke(msgs, config=config), timeout=LLM_TIMEOUT)
        else:
            logger.exception("Unhandled LLM exception")
            response = AIMessage(
                content="⚠️ Sorry, the assistant is temporarily unavailable."
            )

    state["messages"].append(response)
    last_msg = state["messages"][-1]

    if isinstance(last_msg, AIMessage) and last_msg.tool_calls:
        tool_calls = last_msg.tool_calls

        # Normalize tool_calls → list
        if isinstance(tool_calls, dict):
            tool_calls = [tool_calls]
        elif not isinstance(tool_calls, list):
            tool_calls = []

        for call in tool_calls:
            if not isinstance(call, dict):
                continue

            args = call.get("args")

            if not isinstance(args, dict):
                continue

            # ✅ New structured contract: search_args + update_args
            search_args = args.get("search_args")
            update_args = args.get("update_args")

            if isinstance(search_args, dict) and isinstance(update_args, dict):
                search_args["user_id"] = user_id
                update_args["user_id"] = user_id

            # ✅ Legacy / flat args fallback
            else:
                args["user_id"] = user_id

    trace["events"].append({
        "node": "meghx_node",
        "latency_ms": (time.perf_counter() - t0) * 1000,
    })
    return state


async def snapshot_messages_node(state: ChatState, config=None):
    state["__bg_messages__"] = copy.deepcopy(state["messages"])
    return state

# deletion from checkpointer >30 messages 
async def prune_messages_node(state: ChatState, config=None):
    msgs = state["messages"]
    if len(msgs) < HISTORY_SUMMARY_MEMORY_LIMIT:
        return state

    return {
        "messages": [RemoveMessage(id=m.id) for m in msgs[:-2]]
    }




# --------------------- BUILD GRAPH ----------------------------
async def build_graph(db_session=None, checkpointer=None):
    """
    Build and return the compiled graph. Accepts a DB session (no Depends) so callers
    (like main.lifespan) can pass a real session.
    """

    graph = StateGraph(ChatState)
    
    # graph.add_node("inject_memory", inject_memory)
    graph.add_node("meghx_node", meghx_node)
    graph.add_node("parent", await build_graph_parent(checkpointer=checkpointer))
    # graph.add_node("snapshot_messages_node", snapshot_messages_node)
    # graph.add_node("extract_memory_background", extract_memory_background)
    # graph.add_node("prune_messages_node", prune_messages_node)

    # graph.add_edge(START, "inject_memory")
    # graph.add_edge("inject_memory", "meghx_node")
    graph.add_edge(START, "meghx_node")
    graph.add_edge("meghx_node", "parent")
    graph.add_edge("parent", END)
    # graph.add_edge("parent", "snapshot_messages_node")
    # graph.add_edge("snapshot_messages_node", "extract_memory_background")
    # graph.add_edge("extract_memory_background", "prune_messages_node")
    # graph.add_edge("prune_messages_node", END)

    # >>>  DO NOT COMPILE HERE  <<<
    return graph          
