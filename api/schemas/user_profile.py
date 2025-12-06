from pydantic import BaseModel, field_validator
from typing import List, Optional
from datetime import datetime

class ThreadOut(BaseModel):
    id: str
    title: Optional[str]
    created_at: Optional[datetime]

    class Config:
        from_attributes = True  # ✅ important for SQLAlchemy objects

class DocumentOut(BaseModel):
    id: int
    file_name: str
    file_path: str
    file_type: Optional[str]
    status: Optional[str]

    class Config:
        from_attributes = True

class ToolOut(BaseModel):
    id: int
    name: str
    description: Optional[str]
    status: Optional[str]

    class Config:
        from_attributes = True

class UserSettingsOut(BaseModel):
    preferred_model: Optional[str]
    theme: Optional[str]
    notification_enabled: Optional[bool]
    preferred_tools: Optional[list]

    @field_validator("preferred_tools", mode="before")
    def parse_tools(cls, v):
        import json
        if isinstance(v, str):
            return json.loads(v)
        return v


    class Config:
        from_attributes = True

class UserProfile(BaseModel):
    id: int
    name: Optional[str]
    email: str
    created_at: Optional[datetime]
    threads: List[ThreadOut] = []
    documents: List[DocumentOut] = []
    settings: Optional[UserSettingsOut] = None
    tools: List[ToolOut] = []

    class Config:
        from_attributes = True
