"""NSE website host. nseindia.com redirects to nseindia.in since late 2026; override with NSE_HOST."""

import os

NSE_HOST = os.environ.get("NSE_HOST", "https://www.nseindia.in").rstrip("/")
