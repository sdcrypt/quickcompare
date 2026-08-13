"""
Shared scraper settings loaded from the environment.

Set SCRAPER_PINCODE in the project .env file (used by docker-compose for the
scraper service). Both Blinkit and Zepto use this pincode when setting delivery
location before each search.
"""

import os

from dotenv import load_dotenv

load_dotenv()

DEFAULT_PINCODE = os.getenv("SCRAPER_PINCODE", "110001")
