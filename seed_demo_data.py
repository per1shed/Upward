"""Seed progress.db with fictional August data for the three team members."""
from __future__ import annotations

import asyncio
import datetime as dt
import random

from database import DB_PATH, init_db, register_user, upsert_entry

# Same IDs as access.ALLOWED_USER_IDS
USERS: list[tuple[int, str]] = [
    (6205102102, "Диман"),
    (5007535736, "Пашок"),
    (1109190677, "Владос"),
]

YEAR = 2026
MONTH = 8


def _h(hours: int, minutes: int = 0) -> float:
    return hours + minutes / 60.0


async def _clear_month_and_extra_users() -> None:
    import aiosqlite

    allowed = {uid for uid, _ in USERS}
    async with aiosqlite.connect(DB_PATH) as db:
        # Keep only the three team users
        await db.execute(
            f"DELETE FROM users WHERE user_id NOT IN ({','.join('?' * len(allowed))})",
            tuple(allowed),
        )
        await db.execute(
            f"DELETE FROM entries WHERE user_id NOT IN ({','.join('?' * len(allowed))})",
            tuple(allowed),
        )
        # Replace demo month for these users
        await db.execute(
            "DELETE FROM entries WHERE entry_date LIKE ?",
            (f"{YEAR}-{MONTH:02d}-%",),
        )
        await db.commit()


async def seed() -> None:
    random.seed(42)
    await init_db()
    await _clear_month_and_extra_users()

    for uid, name in USERS:
        await register_user(uid, name)

    # Hand-crafted patterns so the chart is easy to “read”
    # day -> {username: (hours, is_rest, is_breakthrough, note)}
    dalron, pavel, vlad = USERS
    plan: dict[int, dict[int, tuple[float, bool, bool, str]]] = {
        1: {
            dalron[0]: (_h(4, 20), False, False, ""),
            pavel[0]: (_h(6, 10), False, False, ""),
            vlad[0]: (_h(3, 0), False, False, ""),
        },
        2: {
            dalron[0]: (_h(5, 45), False, False, ""),
            pavel[0]: (_h(7, 30), False, False, ""),
        },
        3: {
            # rest day for one user
            vlad[0]: (0.0, True, False, ""),
            pavel[0]: (_h(2, 15), False, False, ""),
        },
        4: {
            dalron[0]: (_h(8, 0), False, False, ""),
            pavel[0]: (_h(8, 40), False, False, ""),
            vlad[0]: (_h(5, 20), False, False, ""),
        },
        5: {
            pavel[0]: (_h(9, 5), False, True, "Закрыл сложный баг в проде"),
            vlad[0]: (_h(4, 50), False, False, ""),
        },
        6: {
            dalron[0]: (_h(1, 30), False, False, ""),
            vlad[0]: (_h(6, 0), False, False, ""),
        },
        7: {
            # weekend — lighter
            pavel[0]: (_h(3, 10), False, False, ""),
        },
        8: {
            dalron[0]: (_h(6, 25), False, False, ""),
            pavel[0]: (_h(5, 55), False, False, ""),
            vlad[0]: (_h(7, 15), False, False, ""),
        },
        9: {
            dalron[0]: (0.0, True, False, ""),
            pavel[0]: (_h(4, 0), False, False, ""),
            vlad[0]: (_h(4, 0), False, False, ""),
        },
        10: {
            dalron[0]: (_h(7, 40), False, False, ""),
            pavel[0]: (_h(6, 20), False, False, ""),
            vlad[0]: (_h(2, 45), False, False, ""),
        },
        11: {
            # tall bar near a grid line — label collision case
            pavel[0]: (_h(14, 12), False, False, ""),
            dalron[0]: (_h(3, 30), False, False, ""),
        },
        12: {
            dalron[0]: (_h(5, 0), False, False, ""),
            pavel[0]: (_h(5, 10), False, False, ""),
            vlad[0]: (_h(5, 20), False, False, ""),
        },
        13: {
            # several close heights — labels should stack
            dalron[0]: (_h(6, 50), False, False, ""),
            pavel[0]: (_h(7, 5), False, False, ""),
            vlad[0]: (_h(6, 40), False, True, "Сдал важный этап"),
        },
        14: {
            vlad[0]: (0.0, True, False, ""),
            pavel[0]: (_h(8, 15), False, False, ""),
        },
        15: {
            dalron[0]: (_h(9, 30), False, True, "Разобрал архитектуру модуля"),
            pavel[0]: (_h(4, 45), False, False, ""),
            vlad[0]: (_h(3, 20), False, False, ""),
        },
        16: {
            dalron[0]: (_h(2, 0), False, False, ""),
            pavel[0]: (_h(2, 30), False, False, ""),
            vlad[0]: (_h(10, 5), False, False, ""),
        },
        17: {
            # Sunday
            pavel[0]: (_h(1, 45), False, False, ""),
        },
        18: {
            dalron[0]: (_h(6, 10), False, False, ""),
            pavel[0]: (_h(6, 35), False, False, ""),
            vlad[0]: (_h(6, 55), False, False, ""),
        },
        19: {
            dalron[0]: (_h(4, 15), False, False, ""),
            pavel[0]: (_h(11, 20), False, False, ""),
            vlad[0]: (_h(5, 40), False, False, ""),
        },
        20: {
            # “today” sample — partial day
            dalron[0]: (_h(3, 5), False, False, ""),
            pavel[0]: (_h(5, 50), False, False, ""),
            vlad[0]: (_h(2, 25), False, False, ""),
        },
    }

    for day, by_user in plan.items():
        entry_date = dt.date(YEAR, MONTH, day)
        for uid, (hours, is_rest, is_br, note) in by_user.items():
            name = next(n for i, n in USERS if i == uid)
            await upsert_entry(
                uid,
                entry_date,
                hours,
                name,
                is_rest=is_rest,
                is_breakthrough=is_br,
                breakthrough_note=note,
            )

    print(f"Seeded {DB_PATH}")
    print(f"Users: {', '.join(n for _, n in USERS)}")
    print(f"Month: {YEAR}-{MONTH:02d} ({len(plan)} days with marks)")


if __name__ == "__main__":
    asyncio.run(seed())
