from typing import List, Optional, Sequence

from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_core.tools import BaseTool

from MCP.client import get_mcp_servers
from core.config import EXPENSE_TOOL_NAMES, TOOL_SCOPES
import logging

logger = logging.getLogger(__name__)


async def multiserver_mcpclient_tools(tool_scope: str = "all") -> List[BaseTool]:
    """
    Load tools from all MCP servers registered in `get_mcp_servers()`.

    Parameters
    ----------
    tool_scope : str, optional
        A key into `TOOL_SCOPES` that defines which tools to keep.
        - "all"  -> every tool **except** those listed in `EXPENSE_TOOL_NAMES`
        - any other scope -> only tools whose name is in `TOOL_SCOPES[tool_scope]`

    Returns
    -------
    List[BaseTool]
        Flat list of LangChain-compatible tools.
    """
    try:
        allowed: Optional[Sequence[str]] = TOOL_SCOPES.get(tool_scope)
        servers = get_mcp_servers()
        if not servers:
            return []

        tools: List[BaseTool] = []

        for name, config in servers.items():
            try:
                client = MultiServerMCPClient({name: config})
                server_tools = await client.get_tools()

                # Filtering logic
                if tool_scope == "other":
                    server_tools = [
                        t for t in server_tools
                        if t.name not in EXPENSE_TOOL_NAMES
                    ]
                elif allowed:
                    server_tools = [
                        t for t in server_tools
                        if t.name in allowed
                    ]

                tools.extend(server_tools)

            except Exception:
                logger.exception("MCP server %r failed to load tools", name)

        return tools

    except Exception:
        logger.exception("Unexpected error while loading MCP tools")
        return []