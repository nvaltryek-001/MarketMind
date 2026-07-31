from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()

NSE_BASE_URL = "https://www.nseindia.com"
NSE_API_BASE_URL = f"{NSE_BASE_URL}/api"
BSE_XML_ENDPOINT = "https://api.bseindia.com/BseIndiaAPI/api/AnnSubCategoryGetData/w"

DEFAULT_HEADERS = {
    "user-agent": os.getenv(
        "NSE_USER_AGENT",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    ),
    "accept": "application/json, text/plain, */*",
    "accept-language": "en-US,en;q=0.9",
    "referer": os.getenv("NSE_REFERER", NSE_BASE_URL),
    "x-requested-with": "XMLHttpRequest",
    "connection": "keep-alive",
}

REQUEST_TIMEOUT_SECONDS = float(os.getenv("REQUEST_TIMEOUT_SECONDS", "20"))
REQUESTS_PER_MINUTE = int(os.getenv("REQUESTS_PER_MINUTE", "20"))
MIN_REQUEST_INTERVAL_SECONDS = max(60.0 / REQUESTS_PER_MINUTE, 0.0)
