import httpx
import base64
from fastapi import HTTPException
from core.config import *


def _twitter_basic_auth_header() -> str:
    raw = f"{TWITTER_CLIENT_ID}:{TWITTER_CLIENT_SECRET}"
    encoded = base64.b64encode(raw.encode()).decode()
    return f"Basic {encoded}"

async def exchange_code_for_token_twitter(code: str, verifier: str) -> dict:
    headers = {
        "Authorization": _twitter_basic_auth_header(),
        "Content-Type": "application/x-www-form-urlencoded",
    }

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            TWITTER_TOKEN_URL,
            headers=headers,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": TWITTER_REDIRECT_URI,
                "code_verifier": verifier,
            },
            timeout=10,
        )

    if resp.status_code != 200:
        raise HTTPException(
            status_code=400,
            detail=f"Twitter token exchange failed: {resp.text}",
        )

    return resp.json()



async def fetch_twitter_profile(access_token: str) -> dict:
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            TWITTER_PROFILE_URL,
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10,
        )

    if resp.status_code != 200:
        raise HTTPException(400, resp.text)

    return resp.json()
