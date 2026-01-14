import httpx
from fastapi import HTTPException
from core.config import FB_APP_ID, FB_APP_SECRET, FB_PROFILE_URL, FB_REDIRECT_URI, FB_TOKEN_URL


async def exchange_code_for_token_fb(code: str) -> dict:
    """
    Step 1: Exchange OAuth code for access token
    """
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            FB_TOKEN_URL,
            params={
                "client_id": FB_APP_ID,
                "client_secret": FB_APP_SECRET,
                "redirect_uri": FB_REDIRECT_URI,
                "code": code,
            },
            timeout=10,
        )

    if resp.status_code != 200:
        raise HTTPException(
            status_code=400,
            detail=f"Facebook token exchange failed: {resp.text}",
        )

    return resp.json()


async def fetch_facebook_profile(access_token: str) -> dict:
    """
    Step 2: Fetch user profile
    """
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            FB_PROFILE_URL,
            params={
                "access_token": access_token,
                "fields": "id,name,email",
            },
            timeout=10,
        )

    if resp.status_code != 200:
        raise HTTPException(
            status_code=400,
            detail=f"Facebook profile fetch failed: {resp.text}",
        )

    return resp.json()
