from pydantic import BaseModel

class NotificationStaus(BaseModel):
    notification_enabled: bool
