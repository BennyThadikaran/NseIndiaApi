import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from nse import (  # ruff: ignore[F401]
    NSE,
    CookieStore,
    FileCookieStore,
    MemoryCookieStore,
    _utils,
)
from nse.retry import (  # ruff: ignore[F401]
    STATUS_FORCELIST,
    RetryableStatusError,
    RetryConfig,
    _calculate_wait,
    _parse_retry_after,
    parsedate_to_datetime,
    retry,
)

NSE_FIXED_HOLIDAYS = {
    (1, 26),  # Republic Day
    (4, 14),  # Dr. B. R. Ambedkar Jayanti
    (5, 1),  # Maharashtra Day
    (8, 15),  # Independence Day
    (10, 2),  # Mahatma Gandhi Jayanti
    (12, 25),  # Christmas
}


def get_last_working_date():
    dt = datetime.now() - timedelta(days=1)

    while True:
        # Saturday or Sunday
        if dt.weekday() in (5, 6):
            dt -= timedelta(days=1)
            continue

        # Fixed NSE holiday
        if (dt.month, dt.day) in NSE_FIXED_HOLIDAYS:
            dt -= timedelta(days=1)
            continue

        return dt
