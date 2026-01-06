# graphs/state.py
from typing import Any, Dict, TypedDict, List, Optional, Annotated, Literal
from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage

# class PendingToolCall(TypedDict):
#     name: str
#     args: Dict[str, Any]

class ChatState(TypedDict):
    # Identity
    thread_id: str
    user_id: int

    # canonical context container
    context: Dict[str, Any]

    meta: Dict[str, bool | int | float | str]

    # llm variables
    llm_with_tools: str
    llm_without_tools: str

    # Conversation
    messages: Annotated[list[BaseMessage], add_messages]

    # Routing / Intent
    intent: Optional[Literal["rag", "expense", "other_tool", "chat"]]
    requires_human: bool

    # RAG
    rag_query: Optional[str]
    rag_result: Optional[dict]

    # 🔒 Expense lifecycle
    expense_draft: Optional[Dict[str, Any]]
    expense_search: Optional[Dict[str, Any]]
    expense_update: Optional[Dict[str, Any]]
    expense_confirmed: Optional[bool]
    # MCP (Expenses)
    expense_action: Optional[Literal["record_expense", "record_credit", "update_expense", "remove_expense", "list_user_expenses", "list_cat_subcat_expense", "summarize_user_expenses"]]
    expense_candidates: Optional[list[dict]]
    selected_expense_id: Optional[int]
    hitl_reason: Optional[str]
    pending_confirmation: bool


    # Tool bookkeeping
    last_tool: Optional[str]
    # pending_tool_call: Optional[PendingToolCall]
    tool_call: Optional[str]

    # Evaluation / Guardrails
    safety_flags: Optional[List[str]]


    # LTM memory system ....
    episodic_memories: Optional[list[dict]]
    semantic_memories: Optional[list[dict]]
    procedural_memories: Optional[list[str]]
    long_history_memories: Optional[str]