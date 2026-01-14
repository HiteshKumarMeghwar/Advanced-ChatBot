from sqlalchemy import select
from db.models import UserIntegration

async def get_integration_token(db, user_id: int, provider: str):
    stmt = select(UserIntegration).where(
        UserIntegration.user_id == user_id,
        UserIntegration.provider == provider,
        UserIntegration.is_active == True,
    )
    integration = (await db.execute(stmt)).scalar_one_or_none()
    if not integration:
        return None
    return integration.credentials.get("access_token")
