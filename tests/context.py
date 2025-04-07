import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from nse import NSE


def get_last_working_date():
    dt = datetime.now()

    if dt.hour < 19:
        dt -= timedelta(1)

    while True:
        if dt.weekday() in (5, 6):
            dt -= timedelta(1)
            continue
        return dt
