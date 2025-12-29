from langgraph.graph import StateGraph, START, END
from graphs.state import ChatState
from langgraph.prebuilt import ToolNode
from tools.rag_tool import rag_tool

async def rag_router(state: ChatState):
    if state.get("intent") == "rag":
        return state
    return END

async def build_rag_graph(checkpointer=None):
    g = StateGraph(ChatState)

    g.add_node("rag_router", rag_router)
    g.add_node("tools", ToolNode([rag_tool]))

    g.add_edge(START, "rag_router")
    g.add_edge("rag_router", "tools")
    g.add_edge("tools", END)

    return g.compile(checkpointer=checkpointer)
