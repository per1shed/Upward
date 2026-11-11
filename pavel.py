"""Разделы Tempo для Пашка: план, финансы, состояние, трафик, секундомер, даты."""
from __future__ import annotations

import calendar
import datetime as dt
import json
import os
import subprocess
from typing import Any

import aiosqlite

from access import PASHOK_ID
from database import DB_PATH
from timezone_utils import TZ, now_local, today_local

STAMP = "tempo-import"
KEEP_STAMPS = ("tempo-import", "carry-forward")

TRACKERS = (
    {"slug": "physical", "title": "Физическое", "kind": "scale", "agg": "avg", "unit": "", "sort_order": 1},
    {"slug": "moral", "title": "Моральное", "kind": "scale", "agg": "avg", "unit": "", "sort_order": 2},
    {"slug": "cash", "title": "Деньги", "kind": "number", "agg": "last", "unit": "₽", "sort_order": 3},
    {"slug": "debt", "title": "Долги", "kind": "number", "agg": "last", "unit": "₽", "sort_order": 4},
    {"slug": "balance", "title": "Баланс", "kind": "number", "agg": "last", "unit": "₽", "sort_order": 5},
    {"slug": "weight", "title": "Вес", "kind": "number", "agg": "last", "unit": "кг", "sort_order": 6},
)


def is_pashok(user_id: int | None) -> bool:
    return user_id == PASHOK_ID


def money(value: float | None, *, signed: bool = False) -> str:
    if value is None:
        return "—"
    number = int(round(value))
    if signed and number > 0:
        sign = "+"
    elif number < 0:
        sign = "−"
    else:
        sign = ""
    body = f"{abs(number):,}".replace(",", " ")
    return f"{sign}{body} ₽"


def parse_amount(text: str) -> float | None:
    raw = (text or "").replace("₽", "").replace(" ", "").replace("\u00a0", "").replace("−", "-").replace(",", ".")
    if not raw:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def seasonal_mode(day: dt.date) -> str:
    if day.month in (1, 6, 7, 8):
        return "holiday"
    return "term"


def effective_mode(stored: str, day: dt.date) -> str:
    if stored == "auto":
        return seasonal_mode(day)
    if stored in ("term", "holiday"):
        return stored
    return seasonal_mode(day)


def next_mode(stored: str) -> str:
    order = ("auto", "term", "holiday")
    try:
        index = order.index(stored)
    except ValueError:
        return "auto"
    return order[(index + 1) % len(order)]


def mode_label(stored: str, day: dt.date | None = None) -> str:
    day = day or today_local()
    actual = effective_mode(stored, day)
    actual_ru = "учёба" if actual == "term" else "каникулы"
    if stored == "auto":
        return f"авто · {actual_ru}"
    if stored == "term":
        return "учёба"
    return "каникулы"


def _clock(minutes: int) -> str:
    return f"{(minutes // 60) % 24:02d}:{minutes % 60:02d}"


def _block(start: int, end: int, title: str) -> dict[str, Any]:
    return {"start": start, "end": end, "title": title}


def plan_blocks(day: dt.date, stored_mode: str) -> list[dict[str, Any]]:
    term = effective_mode(stored_mode, day) == "term"
    morning = _block(6 * 60 + 30, 8 * 60, "Утренняя рутина")
    evening = _block(21 * 60, 22 * 60 + 30, "Вечерняя рутина")
    sleep = _block(22 * 60 + 30, 6 * 60 + 30, "Сон")
    gym = _block(8 * 60, 11 * 60, "Зал")
    weekday = day.weekday()
    if weekday == 5:
        return [morning, _block(8 * 60, 22 * 60 + 30, "Отдых"), sleep]
    if weekday in (0, 4):
        if term:
            return [
                morning, gym,
                _block(11 * 60, 11 * 60 + 30, "Бизнес"),
                _block(11 * 60 + 30, 13 * 60, "IT"),
                _block(13 * 60, 20 * 60, "Университет"),
                _block(20 * 60, 21 * 60, "IT"),
                evening, sleep,
            ]
        return [morning, gym, _block(11 * 60, 11 * 60 + 30, "Бизнес"), _block(11 * 60 + 30, 21 * 60, "IT"), evening, sleep]
    if weekday == 2:
        return [morning, gym, _block(11 * 60, 11 * 60 + 30, "Бизнес"), _block(11 * 60 + 30, 21 * 60, "IT"), evening, sleep]
    if weekday == 6:
        return [morning, _block(8 * 60, 9 * 60, "Бизнес"), _block(9 * 60, 21 * 60, "IT"), evening, sleep]
    if term:
        return [
            morning,
            _block(8 * 60, 9 * 60, "Бизнес"),
            _block(9 * 60, 13 * 60, "IT"),
            _block(13 * 60, 20 * 60, "Университет"),
            _block(20 * 60, 21 * 60, "IT"),
            evening, sleep,
        ]
    return [morning, _block(8 * 60, 9 * 60, "Бизнес"), _block(9 * 60, 21 * 60, "IT"), evening, sleep]


def current_block(blocks: list[dict[str, Any]], moment: dt.datetime) -> dict[str, Any] | None:
    minutes = moment.hour * 60 + moment.minute
    if minutes < 6 * 60 + 30:
        return {**blocks[-1], "tail": True}
    for block in blocks:
        start, end = block["start"], block["end"]
        if start <= end:
            if start <= minutes < end:
                return block
        elif minutes >= start:
            return block
    return None


def plan_text(stored_mode: str, moment: dt.datetime | None = None) -> str:
    moment = (moment or now_local()).astimezone(TZ)
    blocks = plan_blocks(moment.date(), stored_mode)
    current = current_block(blocks, moment)
    lines = [f"<b>План</b> · {mode_label(stored_mode, moment.date())}", ""]
    if current:
        lines.append(f"Сейчас · {current['title']} {_clock(current['start'])}–{_clock(current['end'])}")
    shown_tail = False
    if moment.hour * 60 + moment.minute < 6 * 60 + 30:
        sleep = blocks[-1]
        lines.append(f"● {_clock(sleep['start'])}–{_clock(sleep['end'])} {sleep['title']}")
        shown_tail = True
    for block in blocks:
        if shown_tail and block["title"] == "Сон":
            continue
        mark = "● " if current and not current.get("tail") and block is current else ""
        lines.append(f"{mark}{_clock(block['start'])}–{_clock(block['end'])} {block['title']}")
    return "\n".join(lines)


def block_key(moment: dt.datetime, stored_mode: str) -> str:
    local = moment.astimezone(TZ)
    blocks = plan_blocks(local.date(), stored_mode)
    current = current_block(blocks, local)
    if current is None:
        return ""
    return f"{local.date().isoformat()}|{current['title']}|{current['start']}"


def shift_month(year: int, month: int, step: int) -> tuple[int, int]:
    month += step
    while month < 1:
        month += 12
        year -= 1
    while month > 12:
        month -= 12
        year += 1
    return year, month


def month_allowed(year: int, month: int) -> bool:
    today = today_local()
    if (year, month) > (today.year, today.month):
        return False
    return year >= 2020


async def ensure_schema() -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS trackers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                owner_id INTEGER NOT NULL DEFAULT 0,
                slug TEXT NOT NULL,
                title TEXT NOT NULL,
                kind TEXT NOT NULL,
                agg TEXT NOT NULL,
                unit TEXT NOT NULL DEFAULT '',
                enabled INTEGER NOT NULL DEFAULT 1,
                is_template INTEGER NOT NULL DEFAULT 0,
                sort_order INTEGER NOT NULL DEFAULT 0,
                config_json TEXT NOT NULL DEFAULT '{}',
                UNIQUE (owner_id, slug)
            )
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS tracker_logs (
                tracker_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                entry_date TEXT NOT NULL,
                value_num REAL,
                value_text TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL,
                PRIMARY KEY (tracker_id, user_id, entry_date)
            )
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS video_posts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                posted_at TEXT NOT NULL
            )
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS date_counters (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                mode TEXT NOT NULL,
                target_on TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS stopwatches (
                user_id INTEGER PRIMARY KEY,
                status TEXT NOT NULL,
                segment_started_at TEXT,
                elapsed_before REAL NOT NULL DEFAULT 0,
                laps_json TEXT NOT NULL DEFAULT '[]'
            )
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS pavel_profile (
                user_id INTEGER PRIMARY KEY,
                calendar_mode TEXT NOT NULL DEFAULT 'auto',
                finance_goal REAL,
                finance_goal_name TEXT,
                finance_goal_start REAL,
                finance_goal_set_on TEXT,
                pushes_enabled INTEGER NOT NULL DEFAULT 1,
                last_block_key TEXT,
                morning_push_on TEXT,
                evening_push_on TEXT
            )
            """
        )
        for item in TRACKERS:
            await db.execute(
                """
                INSERT INTO trackers (
                    owner_id, slug, title, kind, agg, unit, enabled, is_template, sort_order, config_json
                ) VALUES (0, ?, ?, ?, ?, ?, 1, 1, ?, '{}')
                ON CONFLICT(owner_id, slug) DO NOTHING
                """,
                (item["slug"], item["title"], item["kind"], item["agg"], item["unit"], item["sort_order"]),
            )
        await db.execute(
            "INSERT INTO pavel_profile (user_id) VALUES (?) ON CONFLICT(user_id) DO NOTHING",
            (PASHOK_ID,),
        )
        await db.commit()


async def _tracker_id(db: aiosqlite.Connection, slug: str) -> int:
    cursor = await db.execute("SELECT id FROM trackers WHERE owner_id = 0 AND slug = ?", (slug,))
    row = await cursor.fetchone()
    if row is None:
        raise RuntimeError(f"нет трекера {slug}")
    return int(row[0])


async def profile(user_id: int) -> dict[str, Any]:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT * FROM pavel_profile WHERE user_id = ?", (user_id,))
        row = await cursor.fetchone()
        if row is None:
            await db.execute("INSERT INTO pavel_profile (user_id) VALUES (?)", (user_id,))
            await db.commit()
            cursor = await db.execute("SELECT * FROM pavel_profile WHERE user_id = ?", (user_id,))
            row = await cursor.fetchone()
        columns = [item[0] for item in cursor.description]
        return dict(zip(columns, row))


async def set_profile(user_id: int, **fields: Any) -> None:
    if not fields:
        return
    keys = list(fields)
    values = [fields[key] for key in keys]
    assignments = ", ".join(f"{key} = ?" for key in keys)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO pavel_profile (user_id) VALUES (?) ON CONFLICT(user_id) DO NOTHING",
            (user_id,),
        )
        await db.execute(
            f"UPDATE pavel_profile SET {assignments} WHERE user_id = ?",
            (*values, user_id),
        )
        await db.commit()


async def save_value(user_id: int, slug: str, day: dt.date, value: float) -> None:
    stamp = now_local().isoformat(timespec="seconds")
    async with aiosqlite.connect(DB_PATH) as db:
        tracker_id = await _tracker_id(db, slug)
        await db.execute(
            """
            INSERT INTO tracker_logs (tracker_id, user_id, entry_date, value_num, value_text, updated_at)
            VALUES (?, ?, ?, ?, '', ?)
            ON CONFLICT(tracker_id, user_id, entry_date) DO UPDATE SET
                value_num = excluded.value_num,
                updated_at = excluded.updated_at
            """,
            (tracker_id, user_id, day.isoformat(), value, stamp),
        )
        await db.commit()


async def _logged(db: aiosqlite.Connection, user_id: int, slug: str) -> dict[dt.date, float]:
    tracker_id = await _tracker_id(db, slug)
    cursor = await db.execute(
        """
        SELECT entry_date, value_num FROM tracker_logs
        WHERE tracker_id = ? AND user_id = ? AND value_num IS NOT NULL
        ORDER BY entry_date
        """,
        (tracker_id, user_id),
    )
    rows = await cursor.fetchall()
    return {dt.date.fromisoformat(day): float(value) for day, value in rows}


async def month_series(user_id: int, slug: str, year: int, month: int, *, carry: bool) -> list[float | None]:
    start = dt.date(year, month, 1)
    last = calendar.monthrange(year, month)[1]
    end = dt.date(year, month, last)
    today = today_local()
    async with aiosqlite.connect(DB_PATH) as db:
        logged = await _logged(db, user_id, slug)
    previous = None
    if carry:
        earlier = [day for day in logged if day < start]
        if earlier:
            previous = logged[max(earlier)]
    points: list[float | None] = []
    day = start
    while day <= end:
        if day > today:
            points.append(None)
        elif day in logged:
            previous = logged[day]
            points.append(previous)
        elif carry and previous is not None:
            points.append(previous)
        else:
            points.append(None)
        day += dt.timedelta(days=1)
    return points


async def latest_value(user_id: int, slug: str, year: int, month: int) -> float | None:
    points = await month_series(user_id, slug, year, month, carry=True)
    today = today_local()
    last_day = calendar.monthrange(year, month)[1]
    limit = today.day if (year, month) == (today.year, today.month) else last_day
    for value in reversed(points[:limit]):
        if value is not None:
            return value
    return None


async def video_month(user_id: int, year: int, month: int) -> list[int | None]:
    start = dt.date(year, month, 1)
    last = calendar.monthrange(year, month)[1]
    end = dt.date(year, month, last)
    today = today_local()
    counts = [0] * last
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT posted_at FROM video_posts WHERE user_id = ?", (user_id,))
        rows = await cursor.fetchall()
    for (raw,) in rows:
        stamp = dt.datetime.fromisoformat(str(raw))
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=TZ)
        day = stamp.astimezone(TZ).date()
        if start <= day <= min(end, today):
            counts[day.day - 1] += 1
    points: list[int | None] = []
    for index, count in enumerate(counts, start=1):
        day = dt.date(year, month, index)
        points.append(None if day > today else count)
    return points


async def add_video(user_id: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO video_posts (user_id, posted_at) VALUES (?, ?)",
            (user_id, now_local().isoformat(timespec="seconds")),
        )
        await db.commit()


def _days_word(days: int) -> str:
    n = abs(days) % 100
    n1 = n % 10
    if 11 <= n <= 14:
        return "дней"
    if n1 == 1:
        return "день"
    if 2 <= n1 <= 4:
        return "дня"
    return "дней"


def counter_label(name: str, mode: str, target: dt.date, ref: dt.date | None = None) -> str:
    ref = ref or today_local()
    if mode == "date":
        return f"{name} · {target.strftime('%d.%m.%Y')}"
    if mode == "until":
        days = (target - ref).days
        if days == 0:
            tail = "сегодня"
        elif days > 0:
            tail = f"осталось {days} {_days_word(days)}"
        else:
            tail = f"прошло {abs(days)} {_days_word(days)}"
    else:
        days = (ref - target).days
        tail = f"прошло {days} {_days_word(days)}"
    return f"{name} · {tail}"


async def list_counters(user_id: int) -> list[dict[str, Any]]:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT id, name, mode, target_on FROM date_counters WHERE user_id = ? ORDER BY id",
            (user_id,),
        )
        rows = await cursor.fetchall()
    return [
        {"id": int(row[0]), "name": row[1], "mode": row[2], "target": dt.date.fromisoformat(row[3])}
        for row in rows
    ]


async def add_counter(user_id: int, name: str, mode: str, target: dt.date) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO date_counters (user_id, name, mode, target_on, created_at) VALUES (?, ?, ?, ?, ?)",
            (user_id, name[:40], mode, target.isoformat(), now_local().isoformat(timespec="seconds")),
        )
        await db.commit()


async def delete_counter(user_id: int, counter_id: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "DELETE FROM date_counters WHERE user_id = ? AND id = ?",
            (user_id, counter_id),
        )
        await db.commit()


def parse_date(text: str) -> dt.date | None:
    raw = (text or "").strip().replace("/", ".").replace("-", ".")
    parts = raw.split(".")
    if len(parts) != 3:
        return None
    try:
        day, month, year = (int(part) for part in parts)
    except ValueError:
        return None
    if year < 100:
        year += 2000
    try:
        return dt.date(year, month, day)
    except ValueError:
        return None


async def stopwatch(user_id: int) -> dict[str, Any]:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT status, segment_started_at, elapsed_before, laps_json FROM stopwatches WHERE user_id = ?",
            (user_id,),
        )
        row = await cursor.fetchone()
        if row is None:
            await db.execute(
                "INSERT INTO stopwatches (user_id, status, elapsed_before, laps_json) VALUES (?, 'idle', 0, '[]')",
                (user_id,),
            )
            await db.commit()
            row = ("idle", None, 0.0, "[]")
    try:
        laps = json.loads(row[3] or "[]")
    except json.JSONDecodeError:
        laps = []
    return {
        "status": row[0],
        "started": row[1],
        "elapsed": float(row[2] or 0),
        "laps": [float(item) for item in laps] if isinstance(laps, list) else [],
    }


def elapsed_seconds(state: dict[str, Any]) -> float:
    total = float(state["elapsed"])
    if state["status"] == "running" and state["started"]:
        started = dt.datetime.fromisoformat(state["started"])
        if started.tzinfo is None:
            started = started.replace(tzinfo=TZ)
        total += max(0.0, (now_local() - started.astimezone(TZ)).total_seconds())
    return total


def format_elapsed(seconds: float) -> str:
    total = max(0, int(round(seconds)))
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


async def _save_stopwatch(user_id: int, state: dict[str, Any]) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO stopwatches (user_id, status, segment_started_at, elapsed_before, laps_json)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                status = excluded.status,
                segment_started_at = excluded.segment_started_at,
                elapsed_before = excluded.elapsed_before,
                laps_json = excluded.laps_json
            """,
            (
                user_id,
                state["status"],
                state["started"],
                state["elapsed"],
                json.dumps(state["laps"]),
            ),
        )
        await db.commit()


async def sw_start(user_id: int) -> dict[str, Any]:
    state = await stopwatch(user_id)
    if state["status"] != "running":
        state["status"] = "running"
        state["started"] = now_local().isoformat(timespec="seconds")
        await _save_stopwatch(user_id, state)
    return state


async def sw_pause(user_id: int) -> dict[str, Any]:
    state = await stopwatch(user_id)
    if state["status"] == "running":
        state["elapsed"] = elapsed_seconds(state)
        state["started"] = None
        state["status"] = "paused"
        await _save_stopwatch(user_id, state)
    return state


async def sw_reset(user_id: int) -> dict[str, Any]:
    state = {"status": "idle", "started": None, "elapsed": 0.0, "laps": []}
    await _save_stopwatch(user_id, state)
    return state


async def sw_lap(user_id: int) -> dict[str, Any]:
    state = await stopwatch(user_id)
    if state["status"] == "running":
        state["laps"].append(elapsed_seconds(state))
        state["laps"] = state["laps"][-12:]
        await _save_stopwatch(user_id, state)
    return state


def stopwatch_text(state: dict[str, Any]) -> str:
    labels = {"idle": "остановлен", "running": "идёт", "paused": "пауза"}
    lines = [f"<b>Секундомер</b> · {labels.get(state['status'], state['status'])}", format_elapsed(elapsed_seconds(state))]
    if state["laps"]:
        lines.append("")
        for index, lap in enumerate(state["laps"], start=1):
            lines.append(f"{index}. {format_elapsed(lap)}")
    return "\n".join(lines)


def _tempo_rows(sql: str) -> list[list[str]]:
    docker = "/usr/bin/docker" if os.path.exists("/usr/bin/docker") else "docker"
    proc = subprocess.run(
        [docker, "exec", "-i", "tempo_db", "psql", "-U", "tempo", "-d", "tempo", "-tA", "-F", "\t", "-c", sql],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    return [line.split("\t") for line in proc.stdout.splitlines() if line.strip()]


def _upsert_import(db, tracker_id: int, user_id: int, day: str, value: float) -> str:
    row = db.execute(
        "SELECT updated_at FROM tracker_logs WHERE tracker_id = ? AND user_id = ? AND entry_date = ?",
        (tracker_id, user_id, day),
    ).fetchone()
    if row is not None and row[0] not in KEEP_STAMPS:
        return "kept"
    db.execute(
        """
        INSERT INTO tracker_logs (tracker_id, user_id, entry_date, value_num, value_text, updated_at)
        VALUES (?, ?, ?, ?, '', ?)
        ON CONFLICT(tracker_id, user_id, entry_date) DO UPDATE SET
            value_num = excluded.value_num,
            updated_at = excluded.updated_at
        WHERE tracker_logs.updated_at IN ('tempo-import', 'carry-forward')
        """,
        (tracker_id, user_id, day, value, STAMP),
    )
    return "written"


def import_tempo_for_pashok() -> dict[str, int]:
    """Один перенос отметок Пашка. Чужие пользователи Tempo не читаются."""
    import sqlite3

    user_id = PASHOK_ID
    finance: dict[str, tuple[float, float]] = {}
    for logged_on, cash, debt in _tempo_rows(
        f"""
        SELECT f.logged_on, f.cash, f.debt
        FROM finance_logs f
        JOIN users u ON u.id = f.user_id
        WHERE u.telegram_id = {user_id}
        ORDER BY f.logged_on, f.id
        """
    ):
        finance[logged_on] = (float(cash), float(debt or 0))
    for logged_on, cash, debt in _tempo_rows(
        f"""
        SELECT s.finance_updated_on, s.finance_cash, s.finance_debt
        FROM user_settings s
        JOIN users u ON u.id = s.user_id
        WHERE u.telegram_id = {user_id}
          AND s.finance_updated_on IS NOT NULL
          AND s.finance_cash IS NOT NULL
        """
    ):
        finance.setdefault(logged_on, (float(cash), float(debt or 0)))
    state: dict[str, tuple[float | None, float | None]] = {}
    for logged_on, physical, moral in _tempo_rows(
        f"""
        SELECT s.logged_on,
               AVG(s.physical) FILTER (WHERE s.physical IS NOT NULL),
               AVG(s.moral) FILTER (WHERE s.moral IS NOT NULL)
        FROM state_checkins s
        JOIN users u ON u.id = s.user_id
        WHERE u.telegram_id = {user_id}
        GROUP BY s.logged_on
        """
    ):
        state[logged_on] = (
            float(physical) if physical else None,
            float(moral) if moral else None,
        )
    settings = _tempo_rows(
        f"""
        SELECT s.calendar_mode, s.pushes_enabled,
               s.finance_goal, s.finance_goal_name, s.finance_goal_start, s.finance_goal_set_on
        FROM user_settings s
        JOIN users u ON u.id = s.user_id
        WHERE u.telegram_id = {user_id}
        """
    )
    counters = _tempo_rows(
        f"""
        SELECT c.name, c.mode, c.target_on
        FROM date_counters c
        JOIN users u ON u.id = c.user_id
        WHERE u.telegram_id = {user_id}
        """
    )
    db = sqlite3.connect(DB_PATH)
    try:
        ids = {slug: int(row[0]) for slug, row in (
            (item["slug"], db.execute("SELECT id FROM trackers WHERE owner_id = 0 AND slug = ?", (item["slug"],)).fetchone())
            for item in TRACKERS
        ) if row is not None}
        written = 0
        for day, (cash, debt) in finance.items():
            for slug, value in (("cash", cash), ("debt", debt), ("balance", cash - debt)):
                if _upsert_import(db, ids[slug], user_id, day, value) == "written":
                    written += 1
        for day, (physical, moral) in state.items():
            if physical is not None and _upsert_import(db, ids["physical"], user_id, day, physical) == "written":
                written += 1
            if moral is not None and _upsert_import(db, ids["moral"], user_id, day, moral) == "written":
                written += 1
        if settings:
            mode, pushes, goal, goal_name, goal_start, goal_on = settings[0]
            db.execute(
                """
                INSERT INTO pavel_profile (
                    user_id, calendar_mode, pushes_enabled, finance_goal, finance_goal_name,
                    finance_goal_start, finance_goal_set_on
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    calendar_mode = excluded.calendar_mode,
                    pushes_enabled = excluded.pushes_enabled,
                    finance_goal = excluded.finance_goal,
                    finance_goal_name = excluded.finance_goal_name,
                    finance_goal_start = excluded.finance_goal_start,
                    finance_goal_set_on = excluded.finance_goal_set_on
                """,
                (
                    user_id,
                    mode or "auto",
                    1 if pushes in ("t", "true", "1") else 0,
                    float(goal) if goal else None,
                    goal_name or None,
                    float(goal_start) if goal_start else None,
                    goal_on or None,
                ),
            )
        for name, mode, target in counters:
            exists = db.execute(
                "SELECT 1 FROM date_counters WHERE user_id = ? AND name = ? AND target_on = ?",
                (user_id, name, target),
            ).fetchone()
            if exists is None:
                db.execute(
                    "INSERT INTO date_counters (user_id, name, mode, target_on, created_at) VALUES (?, ?, ?, ?, ?)",
                    (user_id, name, mode, target, now_local().isoformat(timespec="seconds")),
                )
        db.commit()
    finally:
        db.close()
    return {"finance_days": len(finance), "state_days": len(state), "counters": len(counters), "written": written}
