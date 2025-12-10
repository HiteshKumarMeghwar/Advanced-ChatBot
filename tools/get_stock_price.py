from langchain_core.tools import tool
from core.config import ALPHAVANTAGE_API_KEY, ALPHAVANTAGE_BASE_URL, INTERNAL_TIMEOUT
import httpx



# Stock price tool ................
@tool
async def get_stock_price(symbol: str) -> dict:

    """Fetch latest stock price for a symbol via Alpha-Vantage."""

    params = {
        "function": "GLOBAL_QUOTE",
        "symbol": symbol,
        "apikey": ALPHAVANTAGE_API_KEY
    }
    async with httpx.AsyncClient(timeout=INTERNAL_TIMEOUT) as client:
        try:
            r = await client.get(ALPHAVANTAGE_BASE_URL.rstrip("/"), params=params)
            r.raise_for_status()
            data = r.json()

            # Alpha-Vantage returns 200 even when symbol is missing;
            # check its internal error message
            if "Error Message" in data:
                return {"error": data["Error Message"]}
            if "Note" in data:          # rate-limit / throttle message
                return {"error": data["Note"]}
            return data
        except Exception as exc:
            return {"error": str(exc)}