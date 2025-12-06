from core.config import MCP_EXPENSE_SERVER_LOCAL, MCP_PATH_REMOTE_MATH_SERVER


# =================== MPC Client ===================
SERVERS = {
    "expense": {
        "transport": "stdio",
        "command": "uv",
        "args": [
            "run", "--with", "fastmcp", "fastmcp", "run", str(MCP_EXPENSE_SERVER_LOCAL)
        ]
    },
    "math": {
        "transport": "streamable_http",
        "url": str(MCP_PATH_REMOTE_MATH_SERVER)
    }
}
