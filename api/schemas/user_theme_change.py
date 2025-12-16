from pydantic import BaseModel, Field
from typing import Literal

class UserThemeChange(BaseModel):
    theme: Literal["light", "dark"] = Field(
        description="User-level tool permission sets itself"
    )
