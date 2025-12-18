# graphs/chat_graph.py
from langchain_core.messages import SystemMessage
from langgraph.graph import StateGraph, START
from langgraph.prebuilt import ToolNode, tools_condition

from tools.gather_tools import gather_tools
from services.chat_model import ChatModelCreator
from core.config import CHAT_MODEL, CHAT_MODEL_TEXT
from graphs.state import ChatState
import logging

logger = logging.getLogger(__name__)

# ------------------ CHATBOT INSTANCE ----------------------
generator_llm = None
llm_with_tools = None


# --------------------- CHAT NODE ------------------------------
async def chat_node(state: ChatState, config=None):
    thread_id = None
    if config and isinstance(config, dict):
        thread_id = config.get("configurable", {}).get("thread_id")

    system_message = SystemMessage(
            content=(
                "You are the reasoning engine behind an AI assistant. "
                "Your job is to produce polished, user-friendly responses.\n\n"

                "========================\n"
                "TOOL USAGE RULES\n"
                "========================\n"
                "• If the user asks about anything in the uploaded PDF, including summaries, topics, "
                "architecture explanations, breakdowns, or insights, you MUST call `rag_tool`.\n"
                f"• Always include the thread_id `{str(thread_id)}` when calling the tool.\n"
                "• Do NOT answer from your own knowledge when a tool is required.\n\n"

                "========================\n"
                "AFTER TOOL CALL RETURNS\n"
                "========================\n"
                "When the `rag_tool` returns content below: \n"
                "1) If `rag_tool` returns the literal string **'NO_DOCS_UPLOADED'** you MUST **NOT** call the tool again."
                "Instead reply:"
                "There are no documents uploaded yet. Please upload a file first, then ask about it."
                "2) If `rag_tool` returns the literal string **'NO_INDEX_EXISTS_FOR_THREAD_REUPLOAD_DOCUMENT'** you MUST **NOT** call the tool again."
                "Instead reply:"
                "There are no indexes of documents uploaded yet. Please re-upload a file, then ask about it."
                "3) If the message starts with"  
                "`NO_RELEVANT_CHUNKS:` → answer:"  
                "I couldn't find anything about that in the uploaded documents."  
                "and **do NOT** call the tool again."
                "4) For any other return, summarise the **context** in natural language."

                "When the tool returns content, you MUST:\n"
                "1) Read the returned chunks.\n"
                "2) Discard all raw structure, JSON, metadata, lists, and noise.\n"
                "3) Write a fresh, clean, human-friendly explanation in natural language.\n"
                "4) Format it professionally: headings, bullets, short paragraphs.\n"
                "5) Keep it focused on the user's topic and avoid irrelevant parts.\n"
                "6) NEVER show the tool output directly. NEVER echo raw content.\n\n"

                "========================\n"
                "NORMAL CONVERSATION\n"
                "========================\n"
                "When no tool is needed:\n"
                "• Answer clearly and conversationally.\n"
                "• Avoid technical jargon unless explaining a concept.\n"
                "• Focus on clarity and user experience.\n\n"

                "========================\n"
                "GOAL\n"
                "========================\n"
                "Produce responses that feel like an expert explaining concepts in a simple, "
                "well-structured, and easy-to-read way. Always rewrite and polish anything that comes "
                "from tools before delivering the final answer."
            )
        )

    msgs = [system_message, *state["messages"]]

    for msg in msgs:
        if hasattr(msg, "tool_calls") and msg.tool_calls:
            for tc in msg.tool_calls:
                if tc["name"] == "rag_tool":
                    state["tool_call"] = "rag_tool"
                    break
    
    response = await llm_with_tools.ainvoke(msgs,config=config)

    if hasattr(response, "tool_calls") and response.tool_calls:
        for tc in response.tool_calls:
            if tc["name"] == "rag_tool":
                state["tool_call"] = "rag_tool"
                break

    return {
        "messages": [response],
        "tool_calls": state.get("tool_call")
    }

        

   
# --------------------- BUILD GRAPH ----------------------------
async def build_graph(db_session=None):
    """
    Build and return the compiled graph. Accepts a DB session (no Depends) so callers
    (like main.lifespan) can pass a real session.
    """

    global generator_llm, llm_with_tools

    generator_llm = ChatModelCreator(model_name=CHAT_MODEL, model_task=CHAT_MODEL_TEXT).generator_llm
    tools = await gather_tools()
    llm_with_tools = generator_llm.bind_tools(tools)

    graph = StateGraph(ChatState)
    
    graph.add_node("chat_node", chat_node)
    graph.add_node("tools", ToolNode(tools))
    
    graph.add_edge(START, "chat_node")
    graph.add_conditional_edges("chat_node", tools_condition)
    graph.add_edge("tools", "chat_node")

    return graph.compile()
