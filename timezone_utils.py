from __future__ import annotations

import datetime as dt
import os
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

load_dotenv()

TZ = ZoneInfo(os.getenv("TZ", "Europe/Moscow"))


def now_local() -> dt.datetime:
    return dt.datetime.now(TZ)


def today_local() -> dt.date:
    return now_local().date()
