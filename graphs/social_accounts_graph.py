from langgraph.graph import StateGraph, START, END
from graphs.state import ChatState
from langgraph.prebuilt import ToolNode, tools_condition
from tools.facebook_tool import facebook_profile_tool
from tools.google_tool import google_profile_tool
from tools.github_tool import github_repos_tool
from tools.twitter_tool import twitter_profile_tool


async def social_accounts_router(state: ChatState):
    if state.get("intent") == "social_accounts":
        return state
    return END

async def build_socail_accounts_graph(checkpointer=None):
    g = StateGraph(ChatState)
    tools = [facebook_profile_tool, google_profile_tool, github_repos_tool, twitter_profile_tool]

    g.add_node("social_accounts_router", social_accounts_router)
    g.add_node("tools", ToolNode(tools))

    g.add_edge(START, "social_accounts_router")
    g.add_conditional_edges("social_accounts_router", tools_condition)
    g.add_edge("tools", END)

    return g.compile(checkpointer=checkpointer)
