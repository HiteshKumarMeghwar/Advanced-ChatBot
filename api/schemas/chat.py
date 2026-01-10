from pydantic import BaseModel, UUID4
from datetime import datetime
from typing import Optional, Union

class ChatRequest(BaseModel):
    thread_id: UUID4
    edit_message_id: Optional[int] = None
    query: str
    image_url: Optional[str] = None

class ChatResponse(BaseModel):
    role: str
    content: str
    message_id: Optional[Union[int, str]] = None
    thread_id: Optional[Union[UUID4, str]] = None
    created_at: Optional[datetime] = None

    model_config = {"arbitrary_types_allowed": True}