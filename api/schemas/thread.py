from pydantic import BaseModel, UUID4
from typing import Optional, List, Dict
from datetime import datetime

class ThreadBase(BaseModel):
    title: Optional[str] = "Untitled Thread"

class ThreadCreate(ThreadBase):
    user_id: Optional[int] = None

class MessageSnippet(BaseModel):
    id: int
    role: str
    content: str
    json_metadata: Optional[Dict] = None
    created_at: datetime

    class Config:
        from_attributes = True

class ThreadRead(ThreadBase):
    id: str
    user_id: int
    created_at: datetime
    messages: List[MessageSnippet] | None = None

    class Config:
        from_attributes = True


class ThreadDelete(BaseModel):
    thread_id: UUID4
    deleted_documents: int
    vector_index_removed: bool

