import json
import time
import uuid
from langgraph.graph import StateGraph, START, END
from core.config import EXPENSE_TOOL_NAMES
from graphs.state import ChatState
from langgraph.prebuilt import ToolNode #, tools_condition
from tools.multiserver_mcpclient_tools import multiserver_mcpclient_tools
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.types import interrupt


# -----------------------------
# NODE: ROUTER
# -----------------------------
async def expense_router(state: ChatState):
    if state.get("intent") == "expense":
        return state
    return END


# -----------------------------
# NODE: MAKING DRAFT FOR ADD/UPDATE/DELETE
# -----------------------------
async def expense_draft_data(state: ChatState, config=None):
    """Route and prepare draft for create/update flows."""
    
    t0 = time.perf_counter()
    trace = config.get("configurable", {}).get("trace")
    action = state.get("expense_action")

    # Prepare draft for create actions
    if action in ("record_expense", "record_credit", "update_expense", "remove_expense"):
        last_msg = state.get("messages")[-1] if state.get("messages") else None
        if last_msg and hasattr(last_msg, "tool_calls") and last_msg.tool_calls:

            tool_call = pick_expense_tool_call(last_msg.tool_calls, action)
            if not tool_call:
                return state
            
            if not is_valid_expense_call(tool_call):
                return state
            
            all_args = normalize_tool_args(tool_call)
            args_update_or_add = all_args["update_args"] or None
            args_search = all_args["search_args"] or None

            state["expense_draft"] = {
                "user_id": args_update_or_add.get("user_id"),
                "amount": args_update_or_add.get("amount"),
                "category": args_update_or_add.get("category") or "miscellaneous",
                "subcategory": args_update_or_add.get("subcategory") or "other",
                "date": args_update_or_add.get("date"),
                "note": args_update_or_add.get("note"),
            }
            state["expense_search"] = args_search
            state["expense_update"] = args_update_or_add

    trace["events"].append({
        "node": "expense_draft_data",
        "latency_ms": (time.perf_counter() - t0) * 1000,
    })

    return state


# -----------------------------
# NODE: AGENT
# -----------------------------
async def expense_agent(state: ChatState, config=None):
    """
    Decide which tool to call and handle HITL logic.
    Fully supports add, update, delete flows.
    """
    config = config or {}
    user_id = config.get("configurable", {}).get("user_id")
    t0 = time.perf_counter()
    trace = config.get("configurable", {}).get("trace")

    if not user_id:
        state["messages"].append(
            AIMessage(content="Please log in to manage expenses.")
        )
        return state

    action = state.get("expense_action")
    draft = state.get("expense_draft")
    expense_search = state.get("expense_search")
    expense_update = state.get("expense_update")
    selected_id = state.get("selected_expense_id")
    candidates = state.get("expense_candidates")

    # Quick-exit for read-only actions (no HITL needed)
    if action in ("list_user_expenses", "summarize_user_expenses", "list_cat_subcat_expense", "random_number", "add"):
        state["last_tool"] = action
        return state


    # -----------------------------
    # CREATE / RECORD
    # -----------------------------
    if action in ("record_expense", "record_credit"):
        if not draft:
            # Missing draft: ask user to provide details (but LLM should have extracted)
            state["messages"].append(AIMessage(content="Please provide expense details like amount, category, etc."))
            return state
        
        if not state.get("expense_confirmed") and not state.get("pending_confirmation"):
            # Ask user for confirmation
            state["pending_confirmation"] = True
            state["hitl_reason"] = "confirm_expense"
            # Ask for confirmation (HITL)

            summary = (
                f"## Confirm Expense\n\n"
                f"- **Amount**: {draft['amount']}\n"
                f"- **Category**: {draft['category']}/{draft['subcategory']}\n"
                f"- **Date**: {draft['date']}\n"
                f"- **Note**: {draft['note']}\n\n"
                f"Reply **YES** to confirm or **NO** to cancel."
            )

            return interrupt({
                "type": "confirm_expense",
                "action": action,
                "draft": draft,
                "message": summary,
                "reason": "User confirmation required for new expense."
            })
        
        # Confirmed → execute tool
        state["last_tool"] = action
        state["pending_confirmation"] = False
        return state

    # -----------------------------
    # UPDATE / DELETE
    # -----------------------------
    if action in ("update_expense", "remove_expense"):
        if selected_id:
            # ID confirmed: proceed to tool
            state["last_tool"] = action
            tool_call_id = f"call_{uuid.uuid4().hex}"
            state["messages"].append(
                AIMessage(
                    content="",
                    tool_calls=[{
                        "id": tool_call_id,
                        "type": "tool_call",
                        "name": action,
                        "args": {
                            "user_id": expense_update.get("user_id"),
                            "expense_id": selected_id,
                            "amount": expense_update.get("amount"),
                            "category": expense_update.get("category"),
                            "subcategory": expense_update.get("subcategory"),
                            "date": expense_update.get("date"),
                            "note": expense_update.get("note"),
                        }
                    }]
                )
            )
            trace["events"].append({
                "node": "expense_agent",
                "latency_ms": (time.perf_counter() - t0) * 1000,
            })
            return state
        
        # If multiple candidates exist → HITL
        if candidates:
            # Interrupt for selection
            state["pending_confirmation"] = True
            state["hitl_reason"] = "expense_selection"

            candidate_list = "\n".join(
                f"- ID: {c['expense_id']}, Amount: {c['amount']}, Date: {c['date']}, Category: {c['category']}"
                for c in candidates
            )
            summary = (
                f"## Select Expense\n\n"
                f"Multiple matches found:\n{candidate_list}\n\n"
                f"Reply with the ID of the one to {action.replace('_', ' ')} (e.g., 'ID: 123')."
            )
            
            return interrupt(
                {
                    "type": "expense_selection",
                    "action": action,
                    "candidates": candidates,
                    "message": summary,
                    "reason": f"User selection required for {action}."
                }
            )
        
        tool_call_id = f"call_{uuid.uuid4().hex}"
        state["messages"].append(
            AIMessage(
                content="",
                tool_calls=[{
                    "id": tool_call_id,
                    "type": "tool_call",
                    "name": "find_expenses",
                    "args": expense_search
                }]
            )
        )
        # No candidates/ID: force find first
        state["last_tool"] = "find_expenses"
        trace["events"].append({
            "node": "expense_agent",
            "latency_ms": (time.perf_counter() - t0) * 1000,
        })
        return state
    

    trace["events"].append({
        "node": "expense_agent",
        "latency_ms": (time.perf_counter() - t0) * 1000,
    })
    # Fallback: no action matched
    return state


# --------------------------------------------------
# NODE: HITL Resume (NO CONFIG MAGIC)
# --------------------------------------------------
async def expense_resume(state: ChatState, config=None):
    """
    Resumes graph after human reply using messages[-1]
    """
    t0 = time.perf_counter()
    trace = config.get("configurable", {}).get("trace")
    last_user_msg = state["messages"][-1]
    if not isinstance(last_user_msg, HumanMessage):
        return state

    tool_name = state["expense_action"]
    draft = state["expense_draft"]
    expense_update = state.get("expense_update")
    candidates = state.get("expense_candidates")
    text = last_user_msg.content.lower()

    # -----------------------------
    # CONFIRMATION FLOW
    # -----------------------------
    if state.get("hitl_reason") == "confirm_expense" and state.get("pending_confirmation"):
        if "yes" in text or "confirm" in text or "ok" in text:
            state["expense_confirmed"] = True
            state["pending_confirmation"] = False
            state["last_tool"] = tool_name
            state["hitl_reason"] = None
            tool_call_id = f"call_{uuid.uuid4().hex}"
            state["messages"].append(
                AIMessage(
                    content="",
                    tool_calls=[{
                        "id": tool_call_id,
                        "type": "tool_call",
                        "name": tool_name,
                        "args": draft
                    }]
                )
            )
            trace["events"].append({
                "node": "expense_resume",
                "latency_ms": (time.perf_counter() - t0) * 1000,
            })
            return state
        elif "no" in text or "cancel" in text:
            state["expense_confirmed"] = False
            state["pending_confirmation"] = False
            state["expense_draft"] = None
            state["hitl_reason"] = None
            state["last_tool"] = None
            state["messages"].append(AIMessage(content="Expense recording cancelled."))
            return state
        else:
            # Retry interrupt
            return interrupt({
                "type": "confirm_expense_retry",
                "action": tool_name,
                "draft": state.get("expense_draft"),
                "message": "Please reply **YES** to confirm or **NO** to cancel.",
                "reason": "Invalid confirmation response."
            })
        
    # -----------------------------
    # SELECTION FLOW
    # -----------------------------
    if state.get("hitl_reason") == "expense_selection" and state.get("pending_confirmation"):
        
        expense_id = await extract_expense_id(text, candidates or [])

        if expense_id is None:
            # Retry interrupt
            return interrupt({
                "type": "expense_selection_retry",
                "action": tool_name,
                "candidates": candidates,
                "message": "Please reply with a valid ID (e.g., 'ID: 123').",
                "reason": "Invalid selection response."
            })
        
        state["selected_expense_id"] = expense_id
        state["pending_confirmation"] = False
        state["hitl_reason"] = None
        state["last_tool"] = tool_name  # Now proceed to update/delete
        tool_call_id = f"call_{uuid.uuid4().hex}"
        state["messages"].append(
            AIMessage(
                content="",
                tool_calls=[{
                    "id": tool_call_id,
                    "type": "tool_call",
                    "name": tool_name,
                    "args": {
                        "user_id": expense_update.get("user_id"),
                        "expense_id": expense_id,
                        "amount": expense_update.get("amount"),
                        "category": expense_update.get("category"),
                        "subcategory": expense_update.get("subcategory"),
                        "date": expense_update.get("date"),
                        "note": expense_update.get("note"),
                    }
                }]
            )
        )
        trace["events"].append({
            "node": "expense_resume",
            "latency_ms": (time.perf_counter() - t0) * 1000,
        })
        return state

    # Fallback: clear pending
    state["pending_confirmation"] = False
    state["hitl_reason"] = None
    trace["events"].append({
        "node": "expense_resume",
        "latency_ms": (time.perf_counter() - t0) * 1000,
    })
    return state


# -----------------------------
# NODE: POST TOOL
# -----------------------------
async def expense_post_tool(state: ChatState, config=None):
    """
    Handle post-tool updates.
    Fully normalized and streaming-safe.
    """
    t0 = time.perf_counter()
    trace = config.get("configurable", {}).get("trace")
    if not state.get("messages"):
        return state

    last = state["messages"][-1]
    if not isinstance(last, ToolMessage):
        return state

    raw = last.content
    tool_name = state.get("expense_action")

    results = normalize_results(raw)

    # --------------------------------------------------
    # STEP 3: Handle find_expenses flow
    # --------------------------------------------------
    if last.name == "find_expenses":
        
        if not results:
            state["messages"].append(
                AIMessage(
                    content=(
                        "I couldn't find any matching expenses for that request. "
                        "Would you like to try a different amount, date, or note?"
                    )
                )
            )

            # 🔴 HARD STOP — clear tool intent
            state["expense_action"] = None
            state["expense_search"] = None
            state["expense_update"] = None
            state["expense_candidates"] = None
            state["selected_expense_id"] = None
            state["pending_confirmation"] = False
            state["hitl_reason"] = None
            state["last_tool"] = None

            trace["events"].append({
                "node": "expense_post_tool",
                "latency_ms": (time.perf_counter() - t0) * 1000,
            })
            return state

        # Single match → auto-select
        if len(results) == 1:
            expense_id = get_expense_id(results[0])
            if expense_id is None:
                raise RuntimeError(
                    f"find_expenses result missing expense_id: {results[0]}"
                )

            state["selected_expense_id"] = expense_id
            state["expense_candidates"] = None
            state["last_tool"] = tool_name
            trace["events"].append({
                "node": "expense_post_tool",
                "latency_ms": (time.perf_counter() - t0) * 1000,
            })
            return state

        # Multiple matches → HITL selection
        normalized_candidates = []
        for row in results:
            expense_id = get_expense_id(row)
            if expense_id is None:
                continue
            normalized_candidates.append({
                **row,
                "expense_id": expense_id,  # enforce canonical key
            })

        if not normalized_candidates:
            state["messages"].append(
                AIMessage(content="Unable to identify expenses from results.")
            )
            trace["events"].append({
                "node": "expense_post_tool",
                "latency_ms": (time.perf_counter() - t0) * 1000,
            })
            return state

        state["expense_candidates"] = normalized_candidates
        state["pending_confirmation"] = True
        state["hitl_reason"] = "expense_selection"
        state["last_tool"] = tool_name
        trace["events"].append({
            "node": "expense_post_tool",
            "latency_ms": (time.perf_counter() - t0) * 1000,
        })
        return state

    # --------------------------------------------------
    # STEP 4: Cleanup after successful non-search tools
    # --------------------------------------------------
    state["expense_draft"] = None
    state["expense_update"] = None
    state["expense_search"] = None
    state["expense_action"] = None
    state["expense_confirmed"] = None
    state["expense_candidates"] = None
    state["selected_expense_id"] = None
    state["pending_confirmation"] = False
    state["hitl_reason"] = None
    state["last_tool"] = None
    trace["events"].append({
        "node": "expense_post_tool",
        "latency_ms": (time.perf_counter() - t0) * 1000,
    })
    return state


# --------------------------------------------------
# STEP 1: Normalize raw tool output into results[]
# --------------------------------------------------
def normalize_results(raw_payload):
    """
    Extracts actual tool results from LangChain ToolMessage content.
    Always returns a list[dict].
    """

    # ToolMessage.content is usually a list of blocks
    if isinstance(raw_payload, list):
        collected = []

        for block in raw_payload:
            # We only care about text blocks
            if isinstance(block, dict) and block.get("type") == "text":
                try:
                    parsed = json.loads(block.get("text", ""))
                except Exception:
                    continue

                if isinstance(parsed, dict) and isinstance(parsed.get("results"), list):
                    collected.extend(parsed["results"])
                elif isinstance(parsed, list):
                    collected.extend(parsed)

        return collected

    # Dict payload
    if isinstance(raw_payload, dict):
        return raw_payload.get("results", [])

    # Raw JSON string
    if isinstance(raw_payload, (str, bytes, bytearray)):
        try:
            parsed = json.loads(raw_payload)
            return parsed.get("results", []) if isinstance(parsed, dict) else []
        except Exception:
            return []

    return []


# --------------------------------------------------
# STEP 2: Canonical expense_id extraction
# --------------------------------------------------
def get_expense_id(row: dict) -> int | None:
    expense_id = row.get("expense_id")

    if isinstance(expense_id, int):
        return expense_id

    if isinstance(expense_id, str) and expense_id.isdigit():
        return int(expense_id)

    return None


# -----------------------------
# HELPER: TOOL ARGUMENTS NORMALIZE (ROOT)
# -----------------------------
def normalize_tool_args(tool_call: dict) -> dict:
    """
    Always returns a dict with:
    {
      "search_args": dict,
      "update_args": dict
    }
    """
    raw = tool_call.get("args") or {}

    # Defensive: unwrap nested args
    if isinstance(raw, dict) and "args" in raw and isinstance(raw["args"], dict):
        raw = raw["args"]

    return {
        "search_args": raw.get("search_args") or {},
        "update_args": raw.get("update_args") or {},
    }

def pick_expense_tool_call(tool_calls: list[dict], action: str):
    for call in tool_calls:
        if call["name"] == action:
            return call
    return None

def is_valid_expense_call(tool_call: dict) -> bool:
    args = tool_call.get("args", {})
    return (
        isinstance(args, dict)
        and "search_args" in args
        and "update_args" in args
    )


# -----------------------------
# HELPER: EXTRACT ID
# -----------------------------
async def extract_expense_id(user_input: str, candidates: list[dict]) -> int | None:
    """Parse expense ID from user response."""
    user_input_lower = user_input.lower()
    for c in candidates:
        id_str = str(c["expense_id"])
        if id_str in user_input or f"id: {id_str}" in user_input_lower:
            return c["expense_id"]
    # Fallback mappings (e.g., "first", "1")
    mapping = {"first": 0, "1": 0, "one": 0, "second": 1, "2": 1, "two": 1, "third": 2, "3": 2, "three": 2}
    idx = mapping.get(user_input_lower, None)
    if idx is not None and idx < len(candidates):
        return candidates[idx]["expense_id"]
    return None


def should_call_tool(state: ChatState):
    if not state.get("messages"):
        return END

    last = state["messages"][-1]

    # 🚫 If no active expense action, never call tools
    if not state.get("expense_action"):
        return END

    if isinstance(last, AIMessage) and last.tool_calls:
        return "tools"

    return END


async def build_expense_graph(checkpointer=None):
    g = StateGraph(ChatState)

    mcp_tools = await multiserver_mcpclient_tools()
    g.add_node("expense_router", expense_router)
    g.add_node("expense_draft_data", expense_draft_data)
    g.add_node("expense_agent", expense_agent)
    g.add_node("expense_resume", expense_resume)
    g.add_node("tools", ToolNode(mcp_tools))
    g.add_node("expense_post_tool", expense_post_tool)

    g.add_edge(START, "expense_router")
    g.add_edge("expense_router", "expense_draft_data")
    g.add_edge("expense_draft_data", "expense_agent")
    g.add_edge("expense_agent", "expense_resume")
    g.add_conditional_edges("expense_resume", should_call_tool)
    g.add_edge("tools", "expense_post_tool")
    g.add_edge("expense_post_tool", "expense_agent")

    return g.compile(checkpointer=checkpointer)
