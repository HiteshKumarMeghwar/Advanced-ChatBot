from core.config import MCP_EXPENSE_SERVER_LOCAL, MCP_PATH_REMOTE_MATH_SERVER
from services.mcp_registry import load_mcp_servers, save_mcp_servers


def bootstrap_mcp_servers():
    servers = load_mcp_servers()
    if servers:
        return  # already initialized

    default_servers = {
        "expense": {
            "transport": "stdio",
            "command": "uv",
            "args": [
                "run", "--with", "fastmcp", "fastmcp", "run",
                str(MCP_EXPENSE_SERVER_LOCAL)
            ]
        },
        "math": {
            "transport": "streamable_http",
            "url": str(MCP_PATH_REMOTE_MATH_SERVER)
        }
    }

    save_mcp_servers(default_servers)
