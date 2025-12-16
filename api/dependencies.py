from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from core.config import COOKIE_NAME, JWT_SECRET, ALGORITHM
from db.models import User
from sqlalchemy.ext.asyncio import AsyncSession
from core.database import get_db
from sqlalchemy import select


# security = HTTPBearer(auto_error=True)   # auto_error=False → allow demo mode

async def get_current_user(
    # cred: HTTPAuthorizationCredentials = Depends(security),
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> User:
    
    token = request.cookies.get(COOKIE_NAME)

    if not token:
        raise HTTPException(status_code=401)
    
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[ALGORITHM])
        user_id = int(payload["sub"])
    except JWTError:
        raise HTTPException(status_code=401)

    # Async ORM query
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalars().first()

    if not user:
        raise HTTPException(status_code=401)

    return user



async def get_current_user_and_token(
    # cred: HTTPAuthorizationCredentials = Depends(security),
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    
    token = request.cookies.get(COOKIE_NAME)

    if not token:
        raise HTTPException(status_code=401)
    
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[ALGORITHM])
        user_id = int(payload["sub"])
    except JWTError:
        raise HTTPException(status_code=401)

    # Fetch user
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalars().first()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Return tuple (User, raw_token)
    return user, token
