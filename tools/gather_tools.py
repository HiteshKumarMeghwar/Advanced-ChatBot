# =================== ALL TOOLS File Import ===================
from tools.search_tool import search_tool
from tools.get_stock_price import get_stock_price
from tools.genderize_tool import get_gender_of_given_name
from tools.rag_tool import rag_tool
from tools.multiserver_mcpclient_tools import multiserver_mcpclient_tools
from typing import List


# =================== Gather All Tools ===================
async def gather_tools() -> List:

    """
    Return *all* tools (sync + async) ready for LangGraph.
    LangGraph 0.2+ accepts both sync and async tools transparently.
    """

    # Await MCP tools and get the actual list
    mcp_tools = await multiserver_mcpclient_tools()

    # Combine all tools into a single flat list
    tools = [search_tool, get_stock_price, get_gender_of_given_name, rag_tool] + mcp_tools
    return tools