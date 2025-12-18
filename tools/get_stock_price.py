from langchain_core.tools import tool
from langchain_core.runnables import RunnableConfig
from core.config import ALPHAVANTAGE_API_KEY, ALPHAVANTAGE_BASE_URL, INTERNAL_TIMEOUT
import httpx



# Stock price tool ................
@tool
async def get_stock_price(symbol: str, config: RunnableConfig) -> dict:

    """Fetch latest stock price for a symbol via Alpha-Vantage."""

    request = config.get("configurable", {}).get("request")

    base = ALPHAVANTAGE_BASE_URL.rstrip("/")
    timeout = httpx.Timeout(INTERNAL_TIMEOUT)
    params = {
        "function": "GLOBAL_QUOTE",
        "symbol": symbol,
        "apikey": ALPHAVANTAGE_API_KEY
    }

    async with httpx.AsyncClient(timeout=timeout, cookies=request.cookies) as client:
        try:
            r = await client.get(base, params=params)
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