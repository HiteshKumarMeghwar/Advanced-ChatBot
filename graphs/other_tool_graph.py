from langgraph.graph import StateGraph, START, END
from graphs.state import ChatState
from langgraph.prebuilt import ToolNode, tools_condition
from tools.multiserver_mcpclient_tools import multiserver_mcpclient_tools
from tools.search_tool import search_tool
from tools.get_stock_price import get_stock_price
from tools.genderize_tool import get_gender_of_given_name


async def other_tool_router(state: ChatState):
    if state.get("intent") == "other_tool":
        return state
    return END

async def build_other_tool_graph(checkpointer=None):
    g = StateGraph(ChatState)
    mcp_tools = await multiserver_mcpclient_tools(tool_scope="other")
    tools = [search_tool, get_stock_price, get_gender_of_given_name] + mcp_tools

    g.add_node("other_tool_router", other_tool_router)
    g.add_node("tools", ToolNode(tools))

    g.add_edge(START, "other_tool_router")
    g.add_conditional_edges("other_tool_router", tools_condition)
    g.add_edge("tools", END)

    return g.compile(checkpointer=checkpointer)
