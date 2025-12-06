from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_core.tools import BaseTool
from MCP.client import SERVERS
from typing import List


_client = MultiServerMCPClient(SERVERS)  # once, globally

# MCP Client have tools .......................
async def multiserver_mcpclient_tools() -> List[BaseTool]:
    
    """List all available MCP tools from your servers."""
    return await _client.get_tools()