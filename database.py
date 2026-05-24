from __future__ import annotations

import calendar
import datetime as dt
from pathlib import Path
from typing import NamedTuple

import aiosqlite

from timezone_utils import today_local

DB_PATH = Path(__file__).resolve().parent / "progress.db"


class DayEntry(NamedTuple):
    hours: float
    is_rest: bool
    is_breakthrough: bool = False


async def _ensure_is_rest_column(db: aiosqlite.Connection) -> None:
    cursor = await db.execute("PRAGMA table_info(entries)")
    columns = {row[1] for row in await cursor.fetchall()}
    if "is_rest" not in columns:
        await db.execute(
            "ALTER TABLE entries ADD COLUMN is_rest INTEGER NOT NULL DEFAULT 0"
        )


async def _ensure_is_breakthrough_column(db: aiosqlite.Connection) -> None:
    cursor = await db.execute("PRAGMA table_info(entries)")
    columns = {row[1] for row in await cursor.fetchall()}
    if "is_breakthrough" not in columns:
        await db.execute(
            "ALTER TABLE entries ADD COLUMN is_breakthrough INTEGER NOT NULL DEFAULT 0"
        )


async def init_db() -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                display_name TEXT NOT NULL DEFAULT '',
                joined_at TEXT NOT NULL
            )
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS entries (
                user_id INTEGER NOT NULL,
                entry_date TEXT NOT NULL,
                hours REAL NOT NULL,
                display_name TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL,
                is_rest INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (user_id, entry_date)
            )
            """
        )
        await _ensure_is_rest_column(db)
        await _ensure_is_breakthrough_column(db)
        await db.commit()


async def register_user(user_id: int, display_name: str) -> None:
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO users (user_id, display_name, joined_at)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                display_name = excluded.display_name
            """,
            (user_id, display_name, now),
        )
        await db.commit()


async def get_registered_users() -> list[tuple[int, str]]:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """
            SELECT user_id, display_name FROM users
            ORDER BY display_name COLLATE NOCASE, user_id
            """
        )
        rows = await cursor.fetchall()
    return [(int(uid), name or f"ID {uid}") for uid, name in rows]


async def user_exists(user_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT 1 FROM users WHERE user_id = ? LIMIT 1",
            (user_id,),
        )
        row = await cursor.fetchone()
    return row is not None


async def upsert_entry(
    user_id: int,
    entry_date: dt.date,
    hours: float,
    display_name: str,
    *,
    is_rest: bool = False,
    is_breakthrough: bool = False,
) -> None:
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO entries (
                user_id, entry_date, hours, display_name, updated_at,
                is_rest, is_breakthrough
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id, entry_date) DO UPDATE SET
                hours = excluded.hours,
                display_name = excluded.display_name,
                updated_at = excluded.updated_at,
                is_rest = excluded.is_rest,
                is_breakthrough = excluded.is_breakthrough
            """,
            (
                user_id,
                entry_date.isoformat(),
                hours,
                display_name,
                now,
                int(is_rest),
                int(is_breakthrough),
            ),
        )
        await db.commit()


async def get_entry(user_id: int, entry_date: dt.date) -> DayEntry | None:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """
            SELECT hours, is_rest, is_breakthrough FROM entries
            WHERE user_id = ? AND entry_date = ?
            """,
            (user_id, entry_date.isoformat()),
        )
        row = await cursor.fetchone()
    if not row:
        return None
    return DayEntry(float(row[0]), bool(row[1]), bool(row[2]))


async def entry_exists(user_id: int, entry_date: dt.date) -> bool:
    return await get_entry(user_id, entry_date) is not None


async def fill_missed_days_for_month(
    user_id: int,
    display_name: str,
    year: int,
    month: int,
) -> None:
    """Прошедшие дни месяца без записи получают 0. Сегодня не трогаем."""
    today = today_local()
    _, last_day = calendar.monthrange(year, month)

    for day in range(1, last_day + 1):
        entry_date = dt.date(year, month, day)
        if entry_date >= today:
            continue
        if not await entry_exists(user_id, entry_date):
            await upsert_entry(user_id, entry_date, 0.0, display_name)


async def fill_all_missed_days() -> None:
    today = today_local()
    for user_id, name in await get_registered_users():
        await fill_missed_days_for_month(user_id, name, today.year, today.month)


async def get_month_entries(
    user_id: int, year: int, month: int
) -> dict[dt.date, DayEntry]:
    prefix = f"{year:04d}-{month:02d}-"
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """
            SELECT entry_date, hours, is_rest, is_breakthrough FROM entries
            WHERE user_id = ? AND entry_date LIKE ?
            """,
            (user_id, f"{prefix}%"),
        )
        rows = await cursor.fetchall()

    result: dict[dt.date, DayEntry] = {}
    for date_str, hours, is_rest, is_breakthrough in rows:
        result[dt.date.fromisoformat(date_str)] = DayEntry(
            float(hours), bool(is_rest), bool(is_breakthrough)
        )
    return result


async def get_breakthroughs_for_year(
    year: int,
) -> list[tuple[int, str, dt.date]]:
    """Все прорывные дни участников за год: (user_id, display_name, date)."""
    prefix = f"{year:04d}-"
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """
            SELECT user_id, display_name, entry_date FROM entries
            WHERE entry_date LIKE ? AND is_breakthrough = 1
            ORDER BY entry_date, display_name COLLATE NOCASE
            """,
            (f"{prefix}%",),
        )
        rows = await cursor.fetchall()
    return [
        (int(user_id), name or f"ID {user_id}", dt.date.fromisoformat(date_str))
        for user_id, name, date_str in rows
    ]


async def get_productive_streak(user_id: int) -> int:
    """Подряд идущие продуктивные дни (hours > 0), считая назад от сегодня.

    День отдыха не увеличивает серию и не прерывает её.
    """
    today = today_local()
    day = today
    today_entry = await get_entry(user_id, today)
    if today_entry is None:
        day = today - dt.timedelta(days=1)
    elif not today_entry.is_rest and today_entry.hours <= 0:
        day = today - dt.timedelta(days=1)

    streak = 0
    while day.year >= 2020:
        entry = await get_entry(user_id, day)
        if entry is None:
            break
        if entry.is_rest or (entry.is_breakthrough and entry.hours <= 0):
            day -= dt.timedelta(days=1)
            continue
        if entry.hours <= 0:
            break
        streak += 1
        day -= dt.timedelta(days=1)
    return streak


async def get_user_stats(user_id: int) -> dict[str, float | int]:
    """Статистика: день с hours > 0 считается одним продуктивным днём."""
    month_start = today_local().replace(day=1).isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """
            SELECT
                COALESCE(SUM(hours), 0),
                COALESCE(SUM(CASE WHEN hours > 0 THEN 1 ELSE 0 END), 0),
                COALESCE(MAX(CASE WHEN hours > 0 THEN hours END), 0)
            FROM entries
            WHERE user_id = ?
            """,
            (user_id,),
        )
        total_hours, productive_days, best_day = await cursor.fetchone()

        cursor = await db.execute(
            """
            SELECT COALESCE(SUM(hours), 0) FROM entries
            WHERE user_id = ? AND entry_date >= ?
            """,
            (user_id, month_start),
        )
        month_hours = (await cursor.fetchone())[0]

    productive_days = int(productive_days or 0)
    total_hours = float(total_hours or 0)
    month_hours = float(month_hours or 0)
    today = today_local()
    days_in_month_so_far = today.day

    return {
        "total_hours": total_hours,
        "productive_days": productive_days,
        "best_day": float(best_day or 0),
        "month_hours": month_hours,
        "streak": await get_productive_streak(user_id),
        "avg_daily": (
            month_hours / days_in_month_so_far if days_in_month_so_far else 0.0
        ),
    }


async def get_display_name(user_id: int) -> str | None:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """
            SELECT display_name FROM entries
            WHERE user_id = ? AND display_name != ''
            ORDER BY updated_at DESC
            LIMIT 1
            """,
            (user_id,),
        )
        row = await cursor.fetchone()
    return row[0] if row else None
