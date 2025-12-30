from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_core.tools import BaseTool
from typing import List
from MCP.client import get_mcp_servers
import logging
logger = logging.getLogger(__name__)


# MCP Client have tools .......................
async def multiserver_mcpclient_tools() -> List[BaseTool]:
    try:
        servers = get_mcp_servers()
        if not servers:
            return []

        tools: List[BaseTool] = []

        for name, config in servers.items():
            try:
                client = MultiServerMCPClient({name: config})
                server_tools = await client.get_tools()
                tools.extend(server_tools)
            except Exception as e:
                logger.error(f"⚠ MCP server '{name}' failed: {e}")

        return tools

    except Exception as e:
        logger.error(f"⚠ MCP tools unavailable: {e}")
        return []