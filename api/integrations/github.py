import httpx
from fastapi import HTTPException
from core.config import *

async def exchange_code_for_token_github(code: str) -> dict:
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            GITHUB_TOKEN_URL,
            headers={"Accept": "application/json"},
            data={
                "client_id": GITHUB_CLIENT_ID,
                "client_secret": GITHUB_CLIENT_SECRET,
                "code": code,
                "redirect_uri": GITHUB_REDIRECT_URI,
            },
            timeout=10,
        )

    if resp.status_code != 200:
        raise HTTPException(400, resp.text)

    return resp.json()


async def fetch_github_profile(access_token: str) -> dict:
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            GITHUB_PROFILE_URL,
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10,
        )

    if resp.status_code != 200:
        raise HTTPException(400, resp.text)

    return resp.json()
