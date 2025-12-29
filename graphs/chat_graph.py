# graphs/chat_graph.py
import asyncio
from langchain_core.messages import SystemMessage, AIMessage
from langgraph.graph import StateGraph, START
from langgraph.prebuilt import ToolNode, tools_condition

from tools.gather_tools import gather_tools
from graphs.bind_tool_with_llm import groq_with_tools_llm
from services.chat_model import ChatModelCreator
from core.config import CHAT_MODEL, CHAT_MODEL_TEXT, LLM_TIMEOUT
from graphs.state import ChatState
import logging

logger = logging.getLogger(__name__)

# ------------------ CHATBOT INSTANCE ----------------------
generator_llm = None
llm_with_tools = None


# --------------------- CHAT NODE ------------------------------
async def chat_node(state: ChatState, config=None):
    thread_id = config.get("configurable", {}).get("thread_id")
    user_id = config.get("configurable", {}).get("user_id")

    # Enhanced system prompt for full auto handling
    system_message = SystemMessage(
        content=(
            "You are the reasoning engine behind an AI assistant. "
            "Your job is to produce polished, user-friendly responses.\n\n"

            "========================\n"
            "TOOL USAGE RULES\n"
            "========================\n"
            "• If the user asks about anything in the uploaded PDF, including summaries, topics, "
            "architecture explanations, breakdowns, or insights, you MUST call `rag_tool`.\n"
            f"• Always include the thread_id = `{str(thread_id)}` when calling the tool.\n"
            "• Do NOT answer from your own knowledge when a tool is required.\n\n"

            "========================\n"
            "AFTER TOOL CALL RETURNS\n"
            "========================\n"
            "When the `rag_tool` returns content below:\n"
            "1) If `rag_tool` returns **'NO_DOCS_UPLOADED'**, do NOT call the tool again. "
            "Reply: There are no documents uploaded yet. Please upload a file first.\n"
            "2) If `rag_tool` returns **'NO_INDEX_EXISTS_FOR_THREAD_REUPLOAD_DOCUMENT'**, "
            "do NOT call the tool again. Reply: No indexed documents exist yet.\n"
            "3) If the message starts with **'NO_RELEVANT_CHUNKS:'**, reply: "
            "I couldn't find anything about that in the uploaded documents.\n"
            "4) Otherwise, summarise the returned context naturally.\n\n"

            "When the tool returns content, you MUST:\n"
            "• Read and understand the content.\n"
            "• Remove raw JSON, metadata, IDs, and noise.\n"
            "• Rewrite in clear, human language.\n"
            "• Structure with headings, lists, and spacing.\n"
            "• NEVER expose raw tool output.\n\n"

            "========================\n"
            "EXPENSE OPERATIONS (CRITICAL DATA SAFETY RULES)\n"
            "========================\n"
            "The assistant can add, update, or delete expenses. These actions MUST follow identity rules.\n\n"

            "• Every expense ALWAYS belongs to a specific user.\n"
            "• `user_id` represents ownership and MUST always be respected.\n\n"

            "ADD / RECORD EXPENSE:\n"
            f"• Use ONLY `user_id` = `{str(user_id)}`.\n"
            f"• Never invent or assume an expense_id.\n\n"

            "========================\n"
            "EXPENSE OPERATIONS RULES (FULL AUTO HANDLING)\n"
            "========================\n"
            "• Every expense belongs to a specific user (`user_id`).\n"
            "• For add/record/credit: Call tool directly with extracted params (date, amount, category, subcategory, note). Use defaults if missing (e.g., category='miscellaneous', subcategory='other').\n"
            "• For list/summarize: Call tool directly with filters if provided.\n"
            "• For find: Call if needed to locate expenses.\n"
            "• For update/delete: ALWAYS call `find_expenses` first if no expense_id in state.\n"
            "  - If 0 matches: Reply 'No matching expenses found.' and stop.\n"
            "  - If 1 match: Auto-set expense_id in state and call update/delete with params.\n"
            "  - If multiple matches: List them clearly (id, date, amount, category) and ask user to choose one (e.g., 'Which one? Reply with ID: 123'). On next turn, parse user response for ID, set expense_id in state, then call update/delete.\n"
            "• Never assume or guess expense_id—always confirm via find or user input.\n"
            "• Use natural language for interactions; handle retries if parse fails.\n"
            "• Validate ownership automatically via tools (they check user_id).\n\n"

            "If required identifiers are missing:\n"
            "• Ask the user politely for the missing information before calling tools.\n\n"

            "========================\n"
            "STATE & MEMORY RULES\n"
            "========================\n"
            "• Save all messages per `thread_id` to maintain conversation context.\n"
            "• Use short-term memory for recent queries and long-term memory for persistent info.\n"
            "• Always refer to prior conversation for follow-ups.\n"
            "• NEVER forget user identity or prior expense context within the same thread.\n"
            "• Track pending actions in state (e.g., pending_expense_action = {'action': 'delete', 'candidates': [...]}).\n"
            "• On tool return, update state accordingly (e.g., set expense_id if confirmed).\n"
            "• Use pending_confirmation = true/false in state to track if user input is needed for multi-match scenarios.\n"
            "• When pending_confirmation is true, parse next user message for ID; if valid, set expense_id and proceed with action; if invalid, ask again.\n"
            "• Reset pending_confirmation to false after successful action or cancellation.\n\n"

            "========================\n"
            "NORMAL CONVERSATION\n"
            "========================\n"
            "When no tool is needed:\n"
            "• Be conversational, calm, and professional.\n"
            "• Avoid unnecessary jargon.\n"
            "• Focus on helping the user feel confident and understood.\n\n"

            "========================\n"
            "UI & MARKDOWN RENDERING RULES (VERY IMPORTANT)\n"
            "========================\n"
            "The frontend renders responses using ReactMarkdown with custom UI components.\n"
            "Your output MUST be optimized for visual clarity and beauty.\n\n"

            "Formatting rules you MUST follow:\n"
            "• Use Markdown headings (#, ##, ###) generously to structure content.\n"
            "• Prefer short paragraphs over long blocks of text.\n"
            "• Use bullet lists instead of inline sentences when listing items.\n"
            "• Use **bold** for emphasis and *italics* for soft highlights.\n"
            "• Use blockquotes (>) for notes, tips, or important warnings.\n"
            "• Use tables when comparing or listing structured data.\n"
            "• Use fenced code blocks (```language) ONLY when showing code.\n"
            "• NEVER dump raw logs, stack traces, or JSON unless explicitly requested.\n\n"

            "Visual intent:\n"
            "• Responses should feel clean, modern, and well-spaced.\n"
            "• Content should scan well on both desktop and mobile.\n"
            "• Think like a product designer, not a debugger.\n\n"

            "========================\n"
            "GOAL\n"
            "========================\n"
            "Deliver answers that are safe, accurate, beautifully formatted, and pleasant to read. "
            "Every response should feel production-ready and thoughtfully designed."
        )
    )

    msgs = [system_message, *state["messages"]]

    try:
        groq_llm_with_tools = await groq_with_tools_llm()
        response = await asyncio.wait_for(groq_llm_with_tools.ainvoke(msgs, config=config), timeout=LLM_TIMEOUT)
    except asyncio.TimeoutError:
        logger.error("LLM call timed out")
        response = AIMessage(content="⚠️ Sorry, the assistant is temporarily unavailable.")

    state["messages"].append(response)

    last_msg = state["messages"][-1]

    if hasattr(last_msg, "tool_calls"):
        for call in last_msg.tool_calls:
            # Inject trusted context
            call["args"]["user_id"] = user_id

    return state

        

   
# --------------------- BUILD GRAPH ----------------------------
async def build_graph(db_session=None, checkpointer=None):
    """
    Build and return the compiled graph. Accepts a DB session (no Depends) so callers
    (like main.lifespan) can pass a real session.
    """

    tools = await gather_tools()

    graph = StateGraph(ChatState)
    
    graph.add_node("chat_node", chat_node)
    graph.add_node("tools", ToolNode(tools))
    
    graph.add_edge(START, "chat_node")
    graph.add_conditional_edges("chat_node", tools_condition)
    graph.add_edge("tools", "chat_node")

    # return graph.compile()

    # >>>  DO NOT COMPILE HERE  <<<
    return graph          # <-- raw StateGraph
