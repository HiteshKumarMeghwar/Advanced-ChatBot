from fastapi import APIRouter, HTTPException, Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession
from core.security import pwd_context
from datetime import datetime, timedelta, timezone
from services.limiting import limiter
from sqlalchemy import select
from jose import JWTError, jwt
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
import hashlib
import secrets
import json

from core.config import JWT_SECRET, ALGORITHM, ACCESS_TOKEN_EXPIRE_MINUTES, USAGE_LIMIT, CHAT_MODEL, USER_MEMORY_DEFAULTS, USER_THEME, FRONTEND_URL, COOKIE_NAME, COOKIE_SECURE, COOKIE_SAMESITE, REFRESH_COOKIE_NAME, GOOGLE_CLIENT_ID
from core.database import get_db
from db.models import User, AuthToken, Tool, UserMemorySetting, UserTool, UserSettings
from api.schemas.user import UserCreate, UserLogin, Token, ForgotPassword, ResetPassword
from services.redis import save_reset_token, get_reset_user, delete_token
from services.mail import send_email



router = APIRouter(prefix="/auth", tags=["Auth"])


# ---------- routes ----------
@router.post("/signup", response_model=Token)
@limiter.limit("5/minute;100/day")
async def signup(
    request: Request,
    user: UserCreate, 
    response: Response, 
    db: AsyncSession = Depends(get_db)
):
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
    await db.flush()   # <-- THIS IS NON-NEGOTIABLE

    # ---- grant tools ----
    await _grant_tools_to_user(db, new_user.id)
    # ---- grant default settings ----
    await _create_default_settings(db, new_user.id)
    # ---- grant memory settings ----
    await _create_default_memory_settings(db, new_user.id)

    # 3. create JWT + expiry for access token ....................................
    access_token, expires_at = _create_access_token(data={"sub": str(new_user.id)})
    # set cookie for access token ................................................
    _set_token_cookie(response, access_token, expires_at, "access_token")

    # for refresh token ..........................................................
    refresh_token, refresh_expires_at = _create_refresh_token(data={"sub": str(new_user.id)})
    # set cookie for refresh token ................................................
    _set_token_cookie(response, refresh_token, refresh_expires_at, "refresh_token")

    # 4. store token hash in AuthToken
    token_hash = hashlib.sha256(refresh_token.encode()).hexdigest()
    db_token = AuthToken(
        user_id=new_user.id,
        token_hash=token_hash,
        expires_at=refresh_expires_at
    )
    db.add(db_token)

    await db.commit()

    # 5. respond
    return {"access_token": access_token, "token_type": "bearer"}

@router.post("/login", response_model=Token)
@limiter.limit("5/minute;100/day")
async def login(
    request: Request, 
    response: Response, 
    user: UserLogin, 
    db: AsyncSession = Depends(get_db)
):
    stmt = select(User).where(User.email == user.email)
    result = await db.execute(stmt)
    db_user = result.scalar_one_or_none()

    if not db_user:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    if not _verify_password(user.password, db_user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    # create JWT + expiry for access token ....................................
    access_token, expires_at = _create_access_token(data={"sub": str(db_user.id)})
    # set cookie for access token ................................................
    _set_token_cookie(response, access_token, expires_at, "access_token")

    # for refresh token ..........................................................
    refresh_token, refresh_expires_at = _create_refresh_token(data={"sub": str(db_user.id)})
    # set cookie for refresh token ................................................
    _set_token_cookie(response, refresh_token, refresh_expires_at, "refresh_token")

    token_hash = hashlib.sha256(refresh_token.encode()).hexdigest()
    # optional: reuse existing row or create new one each login
    db_token = AuthToken(
        user_id=db_user.id,
        token_hash=token_hash,
        expires_at=refresh_expires_at
    )
    db.add(db_token)
    await db.commit()

    return {"access_token": access_token, "token_type": "bearer"}


@router.post("/logout", status_code=204)
async def logout(request: Request, response: Response, db: AsyncSession = Depends(get_db)):

    refresh_token = request.cookies.get(REFRESH_COOKIE_NAME)
    if refresh_token:
        token_hash = hashlib.sha256(refresh_token.encode()).hexdigest()
        await db.execute(
            AuthToken.__table__.delete().where(AuthToken.token_hash == token_hash)
        )
        await db.commit()

    # clear cookie (set to empty with max_age=0)
    response.delete_cookie(key=COOKIE_NAME, path="/")
    response.delete_cookie(key=REFRESH_COOKIE_NAME, path="/")

    return None


@router.post("/forgot-password", status_code=202)
async def forgot_password(body: ForgotPassword, db: AsyncSession = Depends(get_db)):
    user = await db.scalar(select(User).where(User.email == body.email))
    if not user:
        # do NOT reveal existence
        return {"detail": "If the e-mail exists a reset link was sent."}

    token = secrets.token_urlsafe(32)
    await save_reset_token(user.id, token, ttl_sec=600)
    reset_url = f"{FRONTEND_URL}/reset-password?token={token}&flag={body.flag}"
    if body.flag == "local":
        await send_email(
            user.email,
            "Reset your password",
            f"Click the link (valid 10 min): {reset_url}"
        )
        return {"detail": "If the e-mail exists a reset link was sent.", "access_token": token}
    else:
        await send_email(
            user.email,
            "Create your password",
            f"Click the link (valid 10 min): {reset_url}"
        )
        return {"detail": "If the e-mail exists a create password link was sent.", "access_token": token}

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
    if body.flag == "local":
        return {"detail": "Password updated successfully"}
    else:
        return {"detail": "New password created successfully"}


@router.post("/refresh")
async def refresh_token(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    refresh_token = request.cookies.get(REFRESH_COOKIE_NAME)

    if not refresh_token:
        raise HTTPException(status_code=401)

    # Decode & validate
    try:
        payload = jwt.decode(refresh_token, JWT_SECRET, algorithms=[ALGORITHM])
        if payload.get("type") != "refresh":
            raise HTTPException(status_code=401)
        user_id = int(payload["sub"])
    except JWTError:
        raise HTTPException(status_code=401)

    # Check DB (revocation)
    token_hash = hashlib.sha256(refresh_token.encode()).hexdigest()
    result = await db.execute(
        select(AuthToken).where(AuthToken.token_hash == token_hash)
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=401)

    # Issue new access token
    access_token, expires_at = _create_access_token({"sub": str(user_id)})
    _set_token_cookie(response, access_token, expires_at, "access_token")

    return {"success": True}


@router.post("/google", response_model=Token)
async def google_auth(
    request: Request,
    response: Response,
    body: dict,
    db: AsyncSession = Depends(get_db)
):
    google_token = body.get("token")
    if not google_token:
        raise HTTPException(400, "Missing Google token")

    payload = _verify_google_token(google_token)
    if not payload:
        raise HTTPException(401, "Invalid Google token")

    email = payload["email"]
    name = payload.get("name", email.split("@")[0])

    # 1️⃣ find or create user
    user = await db.scalar(select(User).where(User.email == email))

    if not user:
        user = User(
            name=name,
            email=email,
            password_hash=None,
            auth_provider="google"
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)

        await _grant_tools_to_user(db, user.id)
        await _create_default_settings(db, user.id)
        await db.commit()

        # 2️⃣ issue tokens (same as normal login)
        access_token, expires_at = _create_access_token({"sub": str(user.id)})
        _set_token_cookie(response, access_token, expires_at, "access_token")

        refresh_token, refresh_expires_at = _create_refresh_token({"sub": str(user.id)})
        _set_token_cookie(response, refresh_token, refresh_expires_at, "refresh_token")

        token_hash = hashlib.sha256(refresh_token.encode()).hexdigest()
        db.add(AuthToken(
            user_id=user.id,
            token_hash=token_hash,
            expires_at=refresh_expires_at
        ))
        await db.commit()

        return {"msg": True, "email": email, "access_token": access_token, "token_type": "bearer"}
    
    else:
        return {"msg": False}



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

def _create_refresh_token(data: dict):
    expire = datetime.now(timezone.utc) + timedelta(days=7)
    to_encode = data.copy()
    to_encode.update({
        "exp": expire,
        "type": "refresh"
    })
    token = jwt.encode(to_encode, JWT_SECRET, algorithm=ALGORITHM)
    return token, expire

# helper to set cookie
def _set_token_cookie(response: Response, token: str, expires_at, flag: str):
    if flag == "refresh_token":
        max_age = int((expires_at - datetime.now(timezone.utc)).total_seconds())
        response.set_cookie(
            key=REFRESH_COOKIE_NAME,
            value=token,
            max_age=max_age,
            expires=max_age,
            httponly=True,
            secure=COOKIE_SECURE,
            samesite=COOKIE_SAMESITE,
            path="/"
        )

    elif flag == "access_token":
        # expires_at is a datetime (UTC)
        max_age = int((expires_at - datetime.now(timezone.utc)).total_seconds())
        response.set_cookie(
            key=COOKIE_NAME,
            value=token,
            max_age=max_age,
            expires=max_age,
            httponly=True,
            secure=COOKIE_SECURE,
            samesite=COOKIE_SAMESITE,
            path="/"
        )

def _verify_google_token(token: str):
    try:
        info = id_token.verify_oauth2_token(
            token,
            google_requests.Request(),
            GOOGLE_CLIENT_ID
        )
        return info  # contains email, name, sub, picture
    except Exception:
        return None


async def _grant_tools_to_user(db: AsyncSession, user_id: int) -> None:
    """Insert one row per active tool for a new user."""
    global_tools = (
        await db.execute(
            select(Tool)
            .where(Tool.scope == "global")
        )
    ).scalars().all()

    db.add_all([
        UserTool(
            user_id=user_id,
            tool_id=t.id,
            usage_limit=USAGE_LIMIT,
            status="allowed",
        )
        for t in global_tools
    ])


async def _create_default_settings(db: AsyncSession, user_id: int) -> None:
    """Create a default settings row for a new user with *actual* tool names."""
    global_tools = (
        await db.execute(
            select(Tool)
            .where(Tool.scope == "global")
        )
    ).scalars().all()

    db.add(UserSettings(
        user_id=user_id,
        preferred_model=CHAT_MODEL,
        theme=USER_THEME,
        notification_enabled=True,
        preferred_tools = json.dumps([t.name for t in global_tools])
    ))
    

async def _create_default_memory_settings(db: AsyncSession, user_id: int) -> None:
    settings = UserMemorySetting(
        user_id=user_id,
        **USER_MEMORY_DEFAULTS,
    )
    db.add(settings)