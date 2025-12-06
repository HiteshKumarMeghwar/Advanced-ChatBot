from pydantic import BaseModel, Field
from typing import Literal

class UserToolStatus(BaseModel):
    status: Literal["allowed", "denied"] = Field(
        description="User-level tool permission sets itself"
    )
    tool_id: int
