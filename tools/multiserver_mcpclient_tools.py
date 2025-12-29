from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_core.tools import BaseTool
from MCP.client import SERVERS
from typing import List


_client = MultiServerMCPClient(SERVERS)  # once, globally

# MCP Client have tools .......................
async def multiserver_mcpclient_tools() -> List[BaseTool]:
    
    """List all available MCP tools from your servers."""
    try:
        return await _client.get_tools()
    except Exception as e:
        print(f"Warning: Failed to load MCP tools: {e}")
        return []  # Return empty list on failure