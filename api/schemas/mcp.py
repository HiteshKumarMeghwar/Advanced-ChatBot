from pydantic import BaseModel, Field, HttpUrl
from typing import Literal, Optional, List, Dict

class MCPServerConfig(BaseModel):
    transport: Literal["stdio", "streamable_http", "sse"]
    command: Optional[str] = None
    args: Optional[List[str]] = None
    url: Optional[HttpUrl] = None
    extra: Optional[Dict] = None  # optional custom fields
