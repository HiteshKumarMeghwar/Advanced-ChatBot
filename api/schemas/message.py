from pydantic import BaseModel
from typing import Optional, Dict
from datetime import datetime

class MessageBase(BaseModel):
    role: str
    content: Optional[str] = None
    json_metadata: Optional[Dict] = None

class MessageCreate(MessageBase):
    thread_id: str
    tool_call: Optional[str] = None

class MessageRead(MessageBase):
    id: int
    thread_id: str
    created_at: datetime

    class Config:
        from_attributes = True
