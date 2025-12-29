import asyncio
from langgraph.graph import StateGraph, START, END
from core.config import EXPENSE_TOOL_NAMES
from graphs.bind_tool_with_llm import groq_without_tool_llm
from graphs.other_tool_graph import build_other_tool_graph
from graphs.rag_graph import build_rag_graph
from graphs.expense_graph import build_expense_graph
from graphs.state import ChatState
from core.config import LLM_TIMEOUT
from langchain_core.messages import AIMessage, ToolMessage, SystemMessage
import json
import logging
logger = logging.getLogger(__name__)

groq_generator_llm = None

def _json_safe(obj):
    try:
        json.dumps(obj)
        return obj
    except Exception:
        return str(obj)


async def classify_intent(state: ChatState):
    """
    Classifies intent based on tool calls already decided by the LLM.
    This node MUST be deterministic and side-effect free.
    """

    last_message = state["messages"][-1] if state.get("messages") else None
    intent = "chat"

    if last_message and hasattr(last_message, "tool_calls") and last_message.tool_calls:
        tool_names = {tc["name"] for tc in last_message.tool_calls}

        if "rag_tool" in tool_names:
            intent = "rag"

        elif tool_names & EXPENSE_TOOL_NAMES:
            intent = "expense"
            state["expense_action"] = next(iter(tool_names))

        else:
            intent = "other_tool"

    state["intent"] = intent
    return state


async def post_processor(state: ChatState, config=None) -> ChatState:
    """
    Final normalization & guardrail node.
    - Sanitizes tool outputs
    - Enforces expense lifecycle rules
    - Cleans transient state
    - Prepares UI-safe assistant response
    """

    # Sanitize meta
    state["meta"] = {
        k: _json_safe(v)
        for k, v in (state.get("meta") or {}).items()
    }

    messages = state.get("messages", [])
    safety_flags = state.get("safety_flags") or []

    if not messages:
        return state
    
    BASE_SYSTEM_PROMPT = """
        You are a post-processing and content refinement engine.

        IMPORTANT:
        - You are NOT the primary assistant.
        - You must NOT introduce new facts.
        - You must NOT answer the user again.
        - You must ONLY refine, clean, and format the assistant's LAST message.

        Your output replaces the previous assistant message.

        General Rules:
        • Remove raw JSON, logs, IDs, internal metadata, and tool noise.
        • Preserve the original meaning exactly.
        • Improve clarity, structure, and readability.
        • Use clean, professional, user-friendly language.
        • Output MUST be valid Markdown.
        • Output MUST render cleanly in ReactMarkdown.
        • Never mention tools, system messages, or internal state.

        Your sole responsibility is to transform the assistant's last message
        into clean, readable, production-ready Markdown that renders perfectly
        in ReactMarkdown.
        STRICT FORMATTING RULES (MANDATORY):
        1. Tables MUST contain only inline text.
        - NEVER place lists, headings, or paragraphs inside table cells.
        - If a cell contains multiple items, convert them to:
            • bullet-like inline text separated by <br/>
            • OR rewrite the table into sections if clarity improves.
        2. Lists:
        - Use Markdown lists (- item) ONLY outside tables.
        - Never emit raw HTML tags like <ul>, <li>, <div>, <span>.
        3. Headings:
        - Use clear section headers (##, ###) for structure.
        - Do not over-nest headings.
        4. Paragraphs:
        - Keep paragraphs short (1-3 lines).
        - Prefer lists over dense text.
        5. Tables:
        - Use tables ONLY when comparing structured data.
        - Keep them compact and readable on mobile.
        6. Tone & UX:
        - Professional, calm, confident.
        - No filler phrases.
        - No developer commentary.
        - No hallucinated metadata.
        7. Safety:
        - Never expose raw tool output, JSON, logs, or IDs.
        - If content is unclear, simplify—do not invent.
        FINAL OUTPUT REQUIREMENT:
        - Output MUST be valid Markdown
        - Output MUST render cleanly in ReactMarkdown
        - Output MUST be visually polished and user-friendly
        """
    
    RAG_PROMPT = """
        INTENT: DOCUMENT RETRIEVAL (RAG)

        The content you received comes from uploaded documents.

        RAG RULES (MANDATORY):
        1. If the content equals 'NO_DOCS_UPLOADED':
        → Respond: "There are no documents uploaded yet. Please upload a file first."

        2. If the content equals 'NO_INDEX_EXISTS_FOR_THREAD_REUPLOAD_DOCUMENT':
        → Respond: "No indexed documents exist yet. Please upload a document."

        3. If the content starts with 'NO_RELEVANT_CHUNKS:':
        → Respond: "I couldn't find anything about that in the uploaded documents."

        4. Otherwise:
        • Summarize and explain the document content naturally.
        • Do NOT quote raw chunks.
        • Do NOT mention embeddings, vectors, or retrieval.
        • Present the information as if you personally understood the document.

        Formatting Rules:
        • Use headings (##, ###) to structure answers.
        • Use bullet points for lists.
        • Keep paragraphs short.
        • Prioritize clarity over verbosity.
        • Make the answer easy to scan.

        Tone:
        • Confident
        • Helpful
        • Neutral
        • Professional
        """
    
    EXPENSE_PROMPT = """
        INTENT: EXPENSE OPERATION RESULT

        The content reflects the result of an expense-related action.

        EXPENSE RULES:
        • Never expose internal IDs unless the user explicitly needs them.
        • Never expose raw tool output or JSON.
        • Confirm actions clearly and concisely.
        • If an expense was added, updated, or deleted:
        → Clearly state what changed.
        • If no matching expenses were found:
        → Say so plainly and politely.
        • If user confirmation is required:
        → Ask ONE clear follow-up question.

        Formatting Rules:
        • Prefer short confirmations.
        • Use bullet points for summaries.
        • Use bold for key values (amount, category, date).
        • Do NOT over-explain.
        • Avoid conversational fluff.

        Tone:
        • Calm
        • Precise
        • Reassuring
        • Business-like
        """
    
    OTHER_TOOL_PROMPT = """
        INTENT: GENERIC TOOL OUTPUT

        The content was produced by a non-RAG, non-expense tool.

        RULES:
        • Translate the tool result into plain human language.
        • Remove all technical jargon.
        • Do NOT expose internal structures or parameters.
        • Focus on what the result means for the user.

        Formatting:
        • Clean Markdown
        • Logical sections if needed
        • No raw data dumps

        Tone:
        • Clear
        • Neutral
        • User-focused
        """

    intent = state.get("intent") or "unknown"
    system_prompt = BASE_SYSTEM_PROMPT

    if intent == "rag":
        system_prompt += "\n\n" + RAG_PROMPT
    elif intent == "expense":
        system_prompt += "\n\n" + EXPENSE_PROMPT
    elif intent == "other_tool":
        system_prompt += "\n\n" + OTHER_TOOL_PROMPT

    # -----------------------------
    # 2. EXPENSE LIFECYCLE CLEANUP
    # -----------------------------
    if state.get("intent") == "expense":
        # If we reached post_processor, the expense graph completed
        if not state.get("pending_confirmation"):
            state["expense_draft"] = None
            state["expense_update"] = None
            state["expense_search"] = None
            state["expense_action"] = None
            state["expense_confirmed"] = None
            state["expense_id"] = None

    # -----------------------------
    # 3. RESET TRANSIENT ROUTING FIELDS
    # -----------------------------
    state["intent"] = None
    state["last_tool"] = None
    state["requires_human"] = False

    # -----------------------------
    # 4. SAFETY FLAGS & META
    # -----------------------------
    state["safety_flags"] = list(set(safety_flags))

    state.setdefault("meta", {})
    state["meta"]["post_processed"] = True

    system_message = SystemMessage(content=system_prompt)

    # ----------------------------------------------------------
    # 1.  If the last message is already an AIMessage → skip LLM
    # ----------------------------------------------------------
    if isinstance(messages[-1], AIMessage):
        return state   # or return state unchanged

    # ----------------------------------------------------------
    # 2.  Otherwise build the short list and call the model
    # ----------------------------------------------------------
    msgs = [system_message,messages[-1]]

    try:
        response = await asyncio.wait_for(groq_generator_llm.ainvoke(msgs, config=config), timeout=LLM_TIMEOUT)
        state["messages"][-1] = response
    except asyncio.TimeoutError:
        logger.error("Refine-LLM call timed out")

    return state


async def build_graph_parent(checkpointer=None):
    graph = StateGraph(ChatState)

    global groq_generator_llm
    groq_generator_llm = await groq_without_tool_llm()

    graph.add_node("intent", classify_intent)
    graph.add_node("rag", await build_rag_graph(checkpointer=checkpointer))
    graph.add_node("expense", await build_expense_graph(checkpointer=checkpointer))
    graph.add_node("other_tool", await build_other_tool_graph(checkpointer=checkpointer))
    graph.add_node("post", post_processor)

    graph.add_edge(START, "intent")

    graph.add_conditional_edges(
        "intent",
        lambda s: s["intent"],
        {
            "rag": "rag",
            "expense": "expense",
            "other_tool": "other_tool",
            "chat": END,
        },
    )

    graph.add_edge("rag", "post")
    graph.add_edge("expense", "post")
    graph.add_edge("other_tool", "post")
    graph.add_edge("post", END)

    return graph.compile(checkpointer=checkpointer)
