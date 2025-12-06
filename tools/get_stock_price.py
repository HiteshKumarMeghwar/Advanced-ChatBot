from langchain_core.tools import tool
from core.config import ALPHAVANTAGE_API_KEY, ALPHAVANTAGE_BASE_URL
import requests



# Stock price tool ................
@tool
async def get_stock_price(symbol: str) -> dict:

    """Fetch stock price from Alpha Vantage API."""

    params = {
        "function": "GLOBAL_QUOTE",
        "symbol": symbol,
        "apikey": ALPHAVANTAGE_API_KEY
    }
    return requests.get(ALPHAVANTAGE_BASE_URL, params=params).json()