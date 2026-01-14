# routers/feedback.py
import uuid
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from pydantic import BaseModel
from api.integrations.github import fetch_github_profile, exchange_code_for_token_github
from api.integrations.google import fetch_google_profile, exchange_code_for_token_google
from api.integrations.oauth_revoke import revoke_provider
from api.integrations.twitter import fetch_twitter_profile, exchange_code_for_token_twitter
from core.config import FB_APP_ID, FB_REDIRECT_URI, FRONTEND_URL, GITHUB_AUTH_URL, GITHUB_CLIENT_ID, GITHUB_REDIRECT_URI, GOOGLE_AUTH_URL, GOOGLE_CLIENT_ID, GOOGLE_REDIRECT_URI, TWITTER_AUTH_URL, TWITTER_CLIENT_ID, TWITTER_REDIRECT_URI
from core.database import get_db
from api.dependencies import get_current_user
from db.models import User, UserIntegration
from sqlalchemy.ext.asyncio import AsyncSession
from api.integrations.facebook import (
    exchange_code_for_token_fb,
    fetch_facebook_profile,
)
import secrets, hashlib, base64
from services.redis import get_and_delete_pkce_verifier, save_pkce_verifier


router = APIRouter(prefix="/accounts", tags=["Acounts Integration"])


def generate_pkce():
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()
    ).rstrip(b"=").decode()
    return verifier, challenge


@router.get("/facebook/login")
async def facebook_login(user: User = Depends(get_current_user)):
    state = str(uuid.uuid4())  # CSRF protection (store if you want)

    url = (
        "https://www.facebook.com/v19.0/dialog/oauth"
        f"?client_id={FB_APP_ID}"
        f"&redirect_uri={FB_REDIRECT_URI}"
        "&scope=email,public_profile"
        f"&state={state}"
    )
    return RedirectResponse(url)



@router.get("/facebook/callback")
async def facebook_callback(
    code: str,
    error: str = Query(None),
    error_message: str = Query(None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    
    if error:
        return {"success": False, "error": error, "error_message": error_message}

    if not code:
        return {"success": False, "error": "no_code", "error_message": "Facebook did not return a code."}


    token = await exchange_code_for_token_fb(code)
    profile = await fetch_facebook_profile(token["access_token"])

    stmt = select(UserIntegration).where(
        UserIntegration.user_id == user.id,
        UserIntegration.provider == "facebook",
    )
    existing = (await db.execute(stmt)).scalar_one_or_none()

    if existing:
        existing.credentials = {
            "access_token": token["access_token"],
            "expires_at": token.get("expires_at"),
            "facebook_user_id": profile["id"],
        }
        existing.is_connected = True
        existing.is_active = True
    else:
        db.add(
            UserIntegration(
                user_id=user.id,
                provider="facebook",
                display_name=profile.get("name"),
                credentials={
                    "access_token": token["access_token"],
                    "expires_at": token.get("expires_at"),
                    "facebook_user_id": profile["id"],
                },
                is_connected=True,
                is_active=True,
            )
        )

    await db.commit()

    return RedirectResponse(
        f"{FRONTEND_URL}/chat"
    )


@router.get("/google/login")
async def google_login():
    url = (
        f"{GOOGLE_AUTH_URL}"
        f"?client_id={GOOGLE_CLIENT_ID}"
        f"&redirect_uri={GOOGLE_REDIRECT_URI}"
        f"&response_type=code"
        f"&scope=openid email profile"
        f"&access_type=offline"
        f"&prompt=consent"
    )
    return RedirectResponse(url)


@router.get("/google/callback")
async def google_callback(
    code: str,
    error: str = Query(None),
    error_message: str = Query(None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    
    if error:
        return {"success": False, "error": error, "error_message": error_message}

    if not code:
        return {"success": False, "error": "no_code", "error_message": "Google did not return a code."}
    
    token = await exchange_code_for_token_google(code)
    profile = await fetch_google_profile(token["access_token"])

    stmt = select(UserIntegration).where(
        UserIntegration.user_id == user.id,
        UserIntegration.provider == "google",
    )
    existing = (await db.execute(stmt)).scalar_one_or_none()

    if existing:
        existing.credentials = {
            "access_token": token["access_token"],
            "refresh_token": token.get("refresh_token"),
            "expires_in": token.get("expires_in"),
            "google_user_id": profile["sub"],
            "email": profile.get("email"),
        }
        existing.is_connected = True
        existing.is_active = True
    else:
        db.add(
            UserIntegration(
                user_id=user.id,
                provider="google",
                display_name=profile.get("name"),
                credentials={
                    "access_token": token["access_token"],
                    "refresh_token": token.get("refresh_token"),
                    "expires_in": token.get("expires_in"),
                    "google_user_id": profile["sub"],
                    "email": profile.get("email"),
                },
                is_connected=True,
                is_active=True,
            )
        )

    await db.commit()
    return RedirectResponse(f"{FRONTEND_URL}/chat")


@router.get("/github/login")
async def github_login():
    url = (
        f"{GITHUB_AUTH_URL}"
        f"?client_id={GITHUB_CLIENT_ID}"
        f"&redirect_uri={GITHUB_REDIRECT_URI}"
        f"&scope=read:user user:email"
    )
    return RedirectResponse(url)


@router.get("/github/callback")
async def github_callback(
    code: str,
    error: str = Query(None),
    error_message: str = Query(None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    
    if error:
        return {"success": False, "error": error, "error_message": error_message}

    if not code:
        return {"success": False, "error": "no_code", "error_message": "Github did not return a code."}
    
    token = await exchange_code_for_token_github(code)
    profile = await fetch_github_profile(token["access_token"])

    stmt = select(UserIntegration).where(
        UserIntegration.user_id == user.id,
        UserIntegration.provider == "github",
    )
    existing = (await db.execute(stmt)).scalar_one_or_none()

    if existing:
        existing.credentials = {
            "access_token": token["access_token"],
            "github_user_id": profile["id"],
        }
        existing.is_connected = True
        existing.is_active = True
    else:
        db.add(
            UserIntegration(
                user_id=user.id,
                provider="github",
                display_name=profile.get("login"),
                credentials={
                    "access_token": token["access_token"],
                    "github_user_id": profile["id"],
                },
                is_connected=True,
                is_active=True,
            )
        )

    await db.commit()
    return RedirectResponse(f"{FRONTEND_URL}/chat")



@router.get("/twitter/login")
async def twitter_login():
    verifier, challenge = generate_pkce()
    state = str(uuid.uuid4())
    await save_pkce_verifier(state, verifier)

    url = (
        f"{TWITTER_AUTH_URL}"
        f"?response_type=code"
        f"&client_id={TWITTER_CLIENT_ID}"
        f"&redirect_uri={TWITTER_REDIRECT_URI}"
        f"&scope=tweet.read users.read offline.access"
        f"&state={state}"
        f"&code_challenge={challenge}"
        f"&code_challenge_method=S256"
    )
    return RedirectResponse(url)


@router.get("/twitter/callback")
async def twitter_callback(
    code: str,
    state: str = Query(...),
    error: str = Query(None),
    error_message: str = Query(None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    
    if error:
        return {"success": False, "error": error, "error_message": error_message}

    if not code:
        return {"success": False, "error": "no_code", "error_message": "Twitter did not return a code."}
    
    verifier = await get_and_delete_pkce_verifier(state)
    if not verifier:
        raise HTTPException(400, "PKCE verifier expired or invalid")
    
    token = await exchange_code_for_token_twitter(code, verifier)
    profile = await fetch_twitter_profile(token["access_token"])

    stmt = select(UserIntegration).where(
        UserIntegration.user_id == user.id,
        UserIntegration.provider == "twitter",
    )
    existing = (await db.execute(stmt)).scalar_one_or_none()

    if existing:
        existing.credentials = {
            "access_token": token["access_token"],
            "twitter_user_id": profile["data"]["id"],
        }
        existing.is_connected = True
        existing.is_active = True
    else:
        db.add(
            UserIntegration(
                user_id=user.id,
                provider="twitter",
                display_name=profile["data"]["username"],
                credentials={
                    "access_token": token["access_token"],
                    "twitter_user_id": profile["data"]["id"],
                },
                is_connected=True,
                is_active=True,
            )
        )

    await db.commit()
    return RedirectResponse(f"{FRONTEND_URL}/chat")



@router.get("/integrations")
async def list_integrations(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    stmt = select(UserIntegration).where(UserIntegration.user_id == user.id)
    result = await db.execute(stmt)
    integrations = result.scalars().all()

    return [
        {
            "id": i.id,
            "provider": i.provider,
            "display_name": i.display_name,
            "is_connected": i.is_connected,
            "is_active": i.is_active,
        }
        for i in integrations
    ]


class ToggleIntegration(BaseModel):
    is_active: bool


@router.patch("/integrations/{integration_id}/toggle")
async def toggle_integration(
    integration_id: int,
    body: ToggleIntegration,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    stmt = select(UserIntegration).where(
        UserIntegration.id == int(integration_id),
        UserIntegration.user_id == user.id,
    )
    integration = (await db.execute(stmt)).scalar_one_or_none()

    if not integration:
        raise HTTPException(404, "Integration not found")

    integration.is_active = body.is_active
    await db.commit()

    return {"success": True}



@router.delete("/integrations/{integration_id}")
async def delete_integration(
    integration_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    stmt = select(UserIntegration).where(
        UserIntegration.id == integration_id,
        UserIntegration.user_id == user.id,
    )
    integration = (await db.execute(stmt)).scalar_one_or_none()

    if not integration:
        raise HTTPException(404, "Integration not found")

    # 🔥 REVOKE FIRST (FAIL-SAFE)
    try:
        await revoke_provider(
            integration.provider,
            integration.credentials or {},
        )
    except Exception as e:
        # Log but don't block user
        print(f"[REVOKE FAILED] {integration.provider}: {e}")

    # 🧹 DELETE LOCALLY
    await db.delete(integration)
    await db.commit()

    return {"success": True}
