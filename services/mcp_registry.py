import json
from pathlib import Path
from typing import Dict

MCP_JSON_PATH = Path("MCP/servers/servers.json")

# Add hot-reload capability
SERVERS = {}

def reload_mcp_servers():
    global SERVERS
    SERVERS = load_mcp_servers()
    return SERVERS

def load_mcp_servers() -> dict:
    if not MCP_JSON_PATH.exists():
        MCP_JSON_PATH.write_text("{}")
        return {}

    try:
        content = MCP_JSON_PATH.read_text().strip()
        if not content:
            return {}
        return json.loads(content)
    except json.JSONDecodeError:
        # Corrupt file fallback
        MCP_JSON_PATH.write_text("{}")
        return {}

def mcp_server_by_name(mcp_name: str) -> dict:
    if not MCP_JSON_PATH.exists():
        MCP_JSON_PATH.write_text("{}")
        return {}

    try:
        data = json.loads(MCP_JSON_PATH.read_text() or "{}")
    except json.JSONDecodeError:          # file is corrupt
        MCP_JSON_PATH.write_text("{}")
        return {}
    return data.get(mcp_name, {})         # safe lookup


def save_mcp_servers(servers: Dict) -> None:
    MCP_JSON_PATH.parent.mkdir(parents=True, exist_ok=True)

    with MCP_JSON_PATH.open("w", encoding="utf-8") as f:
        json.dump(servers, f, indent=2)


def add_mcp_server(name: str, config: Dict) -> Dict:
    servers = load_mcp_servers()
    if name in servers:
        return

    servers[name] = config
    save_mcp_servers(servers)
    return servers


def delete_mcp_server(name: str) -> Dict:
    servers = load_mcp_servers()
    if name not in servers:
        raise ValueError("MCP server not found")

    del servers[name]
    save_mcp_servers(servers)
    return servers
