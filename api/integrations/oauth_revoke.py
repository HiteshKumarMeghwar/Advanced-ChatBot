import base64
import httpx
from core.config import (
    GITHUB_CLIENT_ID,
    GITHUB_CLIENT_SECRET,
    TWITTER_CLIENT_ID,
    TWITTER_CLIENT_SECRET,
)

async def revoke_google(token: str):
    async with httpx.AsyncClient() as client:
        await client.post(
            "https://oauth2.googleapis.com/revoke",
            data={"token": token},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=10,
        )


async def revoke_facebook(token: str):
    async with httpx.AsyncClient() as client:
        await client.delete(
            "https://graph.facebook.com/v18.0/me/permissions",
            params={"access_token": token},
            timeout=10,
        )


async def revoke_github(token: str):
    auth = base64.b64encode(
        f"{GITHUB_CLIENT_ID}:{GITHUB_CLIENT_SECRET}".encode()
    ).decode()

    async with httpx.AsyncClient() as client:
        resp = await client.request(
            method="DELETE",
            url=f"https://api.github.com/applications/{GITHUB_CLIENT_ID}/token",
            headers={
                "Authorization": f"Basic {auth}",
                "Accept": "application/vnd.github+json",
                "Content-Type": "application/json",
            },
            json={  # ✅ THIS WORKS HERE
                "access_token": token
            },
            timeout=10,
        )

    if resp.status_code not in (200, 204):
        raise Exception(f"GitHub revoke failed: {resp.text}")


async def revoke_twitter(token: str):
    basic = base64.b64encode(
        f"{TWITTER_CLIENT_ID}:{TWITTER_CLIENT_SECRET}".encode()
    ).decode()

    async with httpx.AsyncClient() as client:
        await client.post(
            "https://api.twitter.com/2/oauth2/revoke",
            headers={
                "Authorization": f"Basic {basic}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data={"token": token},
            timeout=10,
        )


async def revoke_provider(provider: str, credentials: dict):
    token = credentials.get("refresh_token") or credentials.get("access_token")

    if not token:
        return

    if provider == "google":
        await revoke_google(token)
    elif provider == "facebook":
        await revoke_facebook(token)
    elif provider == "github":
        await revoke_github(token)
    elif provider in ("twitter", "x"):
        await revoke_twitter(token)
