import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

import nse.utils as utils  # ruff: ignore[F401]
from nse import (  # ruff: ignore[F401]
    NSE,
    CookieStore,
    FileCookieStore,
    MemoryCookieStore,
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


def get_last_working_date():
    dt = datetime.now() - timedelta(1)

    while True:
        if dt.weekday() in (5, 6):
            dt -= timedelta(1)
            continue
        return dt
