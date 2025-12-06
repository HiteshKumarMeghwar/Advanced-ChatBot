from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from core.config import JWT_SECRET, ALGORITHM
from db.models import User
from sqlalchemy.ext.asyncio import AsyncSession
from core.database import get_db
from sqlalchemy import select


security = HTTPBearer(auto_error=False)   # auto_error=False → allow demo mode

async def get_current_user(
    cred: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> User:

    # Demo mode — no token provided
    if cred is None:
        result = await db.execute(select(User).limit(1))
        user = result.scalars().first()
        if not user:
            raise HTTPException(status_code=401, detail="No demo user found")
        return user

    token = cred.credentials

    # Decode + validate
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[ALGORITHM])
        user_id = int(payload["sub"])
    except (JWTError, ValueError, TypeError):
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    # Async ORM query
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalars().first()

    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    return user




async def get_current_user_and_token(
    cred: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db),
):
    # No token → demo mode
    if cred is None:
        result = await db.execute(select(User).limit(1))
        demo_user = result.scalars().first()
        if not demo_user:
            raise HTTPException(status_code=401, detail="No users in DB for demo mode")
        return demo_user, None

    token = cred.credentials

    # Validate token
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[ALGORITHM])
        user_id = int(payload["sub"])
    except (JWTError, ValueError, TypeError):
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    # Fetch user
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalars().first()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Return tuple (User, raw_token)
    return user, token
