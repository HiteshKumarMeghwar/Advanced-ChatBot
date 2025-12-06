from fastapi import APIRouter, HTTPException, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from core.security import pwd_context
from datetime import datetime, timedelta, timezone
from services.limiting import limiter
from sqlalchemy import select
from jose import jwt
import hashlib
import secrets
import json

from core.config import JWT_SECRET, ALGORITHM, ACCESS_TOKEN_EXPIRE_MINUTES, USAGE_LIMIT, CHAT_MODEL, USER_THEME, FRONTEND_URL
from core.database import get_db
from db.models import User, AuthToken, Tool, UserTool, UserSettings
from api.schemas.user import UserCreate, UserLogin, Token, ForgotPassword, ResetPassword
from services.redis import save_reset_token, get_reset_user, delete_token
from services.mail import send_email



router = APIRouter(prefix="/auth", tags=["Auth"])


# ---------- routes ----------
@router.post("/signup", response_model=Token)
async def signup(user: UserCreate, db: AsyncSession = Depends(get_db)):
    # 1. uniqueness check
    existing = await db.execute(
        User.__table__.select().where(User.email == user.email)
    )
    if existing.first():
        raise HTTPException(status_code=400, detail="Email already registered")

    # 2. create user row
    new_user = User(
        name=user.name,
        email=user.email,
        password_hash = _hash_password(user.password)
    )
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)

    # ---- grant tools ----
    await _grant_tools_to_user(db, new_user.id)
    await _create_default_settings(db, new_user.id)
    await db.commit()          # commit the UserTool rows

    # 3. create JWT + expiry
    access_token, expires_at = _create_access_token(data={"sub": str(new_user.id)})

    # 4. store token hash in AuthToken
    token_hash = hashlib.sha256(access_token.encode()).hexdigest()
    db_token = AuthToken(
        user_id=new_user.id,
        token_hash=token_hash,
        expires_at=expires_at
    )
    db.add(db_token)
    await db.commit()

    # 5. respond
    return {"access_token": access_token, "token_type": "bearer"}

@router.post("/login", response_model=Token)
@limiter.limit("5/minute;100/day")
async def login(request: Request, user: UserLogin, db: AsyncSession = Depends(get_db)):
    stmt = select(User).where(User.email == user.email)
    result = await db.execute(stmt)
    db_user = result.scalar_one_or_none()

    if not db_user:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    if not _verify_password(user.password, db_user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    access_token, expires_at = _create_access_token(data={"sub": str(db_user.id)})
    token_hash = hashlib.sha256(access_token.encode()).hexdigest()

    # optional: reuse existing row or create new one each login
    db_token = AuthToken(
        user_id=db_user.id,
        token_hash=token_hash,
        expires_at=expires_at
    )
    db.add(db_token)
    await db.commit()

    return {"access_token": access_token, "token_type": "bearer"}


@router.post("/logout", status_code=204)
async def logout(request: Request, db: AsyncSession = Depends(get_db)):
    # read bearer token from header
    auth = request.headers.get("authorization")
    if not auth or not auth.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing token")
    token = auth.split(" ")[1]
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    # delete token record (or mark expired)
    await db.execute(AuthToken.__table__.delete().where(AuthToken.token_hash == token_hash))
    await db.commit()
    return None


@router.post("/forgot-password", status_code=202)
async def forgot_password(body: ForgotPassword, db: AsyncSession = Depends(get_db)):
    user = await db.scalar(select(User).where(User.email == body.email))
    if not user:
        # do NOT reveal existence
        return {"detail": "If the e-mail exists a reset link was sent."}

    token = secrets.token_urlsafe(32)
    await save_reset_token(user.id, token, ttl_sec=600)

    reset_url = f"{FRONTEND_URL}/reset-password?token={token}"
    await send_email(
        user.email,
        "Reset your password",
        f"Click the link (valid 10 min): {reset_url}"
    )
    return {"detail": "If the e-mail exists a reset link was sent."}

@router.post("/reset-password")
async def reset_password(body: ResetPassword, db: AsyncSession = Depends(get_db)):
    user_id = await get_reset_user(body.token)
    if not user_id:
        raise HTTPException(400, "Invalid or expired token")

    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(400, "Invalid or expired token")

    # hash and store
    user.password_hash = _hash_password(body.new_password)
    await db.commit()

    expires_at = datetime.now(timezone.utc) + (timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))

    token_hash = hashlib.sha256(body.token.encode()).hexdigest()
    db_token = AuthToken(
        user_id=user_id,
        token_hash=token_hash,
        expires_at=expires_at
    )
    db.add(db_token)
    await db.commit()

    # single-use token
    await delete_token(body.token)
    return {"detail": "Password updated successfully"}



# ---------- helpers ----------
def _hash_password(password: str) -> str:
    password = password.encode("utf-8")[:72].decode("utf-8", errors="ignore")
    return pwd_context.hash(password)

def _verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)

def _create_access_token(data: dict, expires_delta: timedelta | None = None):
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    token = jwt.encode(to_encode, JWT_SECRET, algorithm=ALGORITHM)
    return token, expire   # <-- return BOTH token and its expiry


async def _grant_tools_to_user(db: AsyncSession, user_id: int) -> None:
    """Insert one row per active tool for a new user."""
    # 1. all globally active tools
    active_tools = (
        await db.execute(select(Tool).where(Tool.status == "active"))
    ).scalars().all()

    # 2. build rows
    db.add_all([
        UserTool(
            user_id=user_id,
            tool_id=t.id,
            usage_limit=USAGE_LIMIT,
            status="allowed",
        )
        for t in active_tools
    ])


async def _create_default_settings(db: AsyncSession, user_id: int) -> None:
    """Create a default settings row for a new user with *actual* tool names."""
    active_tools = (
        await db.execute(select(Tool.name).where(Tool.status == "active"))
    ).scalars().all()

    db.add(UserSettings(
        user_id=user_id,
        preferred_model=CHAT_MODEL,
        theme=USER_THEME,
        notification_enabled=True,
        preferred_tools=json.dumps(active_tools),   # ← real names from DB
    ))