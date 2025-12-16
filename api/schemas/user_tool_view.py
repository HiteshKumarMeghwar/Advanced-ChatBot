from pydantic import BaseModel

class UserToolView(BaseModel):
    tools: list[dict]
