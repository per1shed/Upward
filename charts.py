from __future__ import annotations

import asyncio
import calendar
import datetime as dt
import io
from typing import TYPE_CHECKING

import matplotlib

matplotlib.use("Agg")
import matplotlib.colors as mcolors
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import FancyBboxPatch, Patch, Rectangle

from database import (
    DayEntry,
    fill_missed_days_for_month,
    get_breakthroughs_for_year,
    get_display_name,
    get_month_entries,
    get_registered_users,
)
from keyboards import MONTH_NAMES
from time_format import format_duration, format_duration_clock

if TYPE_CHECKING:
    from aiogram.types import BufferedInputFile

# Apple-calm palette (командный график)
BG = "#F7F7F8"
INK = "#1D1D1F"
MUTED = "#8E8E93"
GRID = "#D8D8DC"
GOAL_LINE_COLOR = "#5C5C60"
GOAL_HOURS = 4.0
Y_MAX_DEFAULT = 8.0
REST_MARKER_HEIGHT = 0.55

USER_COLORS = (
    "#4A6FA5",  # steel blue
    "#3A3A3C",  # charcoal
    "#5B9A8B",  # muted teal
    "#C48B7A",  # dusty rose
    "#7A8BB8",  # soft indigo
    "#A3926B",  # warm sand
)
EMPTY_COLOR = "#D8DEE9"
PRODUCTIVE_COLOR = USER_COLORS[0]
HIGHLIGHT_COLOR = "#C97B72"
REST_COLOR = "#8FA4C1"
WEEKDAY_ABBR = ("пн", "вт", "ср", "чт", "пт", "сб", "вс")
WEEKDAY_LABEL_COLOR = MUTED
WEEKEND_LABEL_COLOR = "#C97B72"
BREAKTHROUGH_CELL_COLOR = "#FFF8E1"
EMPTY_USER_BLEND = 0.78


def _pale_user_color(base_color: str) -> str:
    """Непрозрачный бледный оттенок цвета участника для пустых дней."""
    r, g, b = mcolors.to_rgb(base_color)
    mix = EMPTY_USER_BLEND
    return mcolors.to_hex(
        (r * (1 - mix) + mix, g * (1 - mix) + mix, b * (1 - mix) + mix)
    )


def _apply_y_grid(ax) -> None:
    """Горизонтальная сетка на заднем плане, под столбцами."""
    ax.set_axisbelow(True)
    ax.grid(axis="y", linestyle=":", linewidth=0.9, color=GRID, zorder=0)


def _entry_for_day(
    entries: dict[dt.date, DayEntry], day: dt.date
) -> DayEntry:
    return entries.get(day, DayEntry(0.0, False, False))


def _day_is_marked(entry: DayEntry) -> bool:
    """День считается отмеченным, если есть время, отдых или прорыв."""
    return entry.is_rest or entry.is_breakthrough or entry.hours > 0


def _month_total_hours(
    entries: dict[dt.date, DayEntry], all_days: list[dt.date]
) -> float:
    return sum(_entry_for_day(entries, day).hours for day in all_days)


def _day_bar_color(
    entry: DayEntry,
    *,
    highlight: bool = False,
) -> str:
    if highlight:
        return HIGHLIGHT_COLOR
    if entry.is_rest:
        return REST_COLOR
    if entry.hours > 0:
        return PRODUCTIVE_COLOR
    return EMPTY_COLOR


def _apply_day_axis_labels(ax, all_days: list[dt.date]) -> None:
    """День недели на оси, под ним число месяца."""
    day_numbers = [day.day for day in all_days]
    ax.set_xticks(day_numbers)
    ax.set_xticklabels([])
    ax.tick_params(axis="x", pad=2, length=0)

    for day in all_days:
        color = WEEKEND_LABEL_COLOR if day.weekday() >= 5 else MUTED
        ax.text(
            day.day,
            -0.02,
            WEEKDAY_ABBR[day.weekday()],
            transform=ax.get_xaxis_transform(),
            ha="center",
            va="top",
            fontsize=8,
            color=color,
            clip_on=False,
        )
        ax.text(
            day.day,
            -0.085,
            str(day.day),
            transform=ax.get_xaxis_transform(),
            ha="center",
            va="top",
            fontsize=7,
            color=color,
            clip_on=False,
        )


def _style_calm_axes(ax) -> None:
    for spine in ("top", "right", "left", "bottom"):
        ax.spines[spine].set_visible(False)
    ax.tick_params(axis="y", colors=MUTED, labelsize=9, length=0)
    _apply_y_grid(ax)


def _draw_rest_marker(ax, x: float, bar_width: float, user_color: str) -> None:
    """
    Личный отдых в слоте участника: короткий штрихованный маркер + точка.
    Не перекрывает чужие столбцы того же дня.
    """
    w = bar_width * 0.85
    bottom = 0.04
    ax.add_patch(
        FancyBboxPatch(
            (x - w / 2, bottom),
            w,
            REST_MARKER_HEIGHT,
            boxstyle="round,pad=0.01,rounding_size=0.12",
            linewidth=0,
            facecolor=user_color,
            alpha=0.22,
            zorder=3,
        )
    )
    ax.bar(
        x,
        REST_MARKER_HEIGHT,
        width=w,
        bottom=bottom,
        facecolor="none",
        edgecolor=user_color,
        linewidth=1.0,
        hatch="////",
        alpha=0.85,
        zorder=4,
    )
    ax.plot(
        [x],
        [bottom + REST_MARKER_HEIGHT / 2],
        marker="o",
        markersize=3.2,
        color=user_color,
        alpha=0.9,
        zorder=5,
    )


def _annotate_breakthrough(ax, x: float, height: float, color: str) -> None:
    ax.text(
        x,
        height + 0.08,
        "★",
        ha="center",
        va="bottom",
        fontsize=9,
        fontweight="bold",
        color=color,
        zorder=5,
    )


def _render_single_chart(
    entries: dict[dt.date, DayEntry],
    title: str,
    year: int,
    month: int,
    highlight: dt.date | None,
) -> bytes:
    _, last_day = calendar.monthrange(year, month)
    all_days = [dt.date(year, month, day) for day in range(1, last_day + 1)]
    day_entries = [_entry_for_day(entries, day) for day in all_days]
    total_month = sum(e.hours for e in day_entries)

    values: list[float] = []
    for entry in day_entries:
        if entry.is_rest:
            values.append(REST_MARKER_HEIGHT)
        elif entry.is_breakthrough and entry.hours <= 0:
            values.append(REST_MARKER_HEIGHT)
        else:
            values.append(entry.hours)
    max_value = max(values) if values else 1.0

    fig, ax = plt.subplots(figsize=(max(14.0, last_day * 0.48), 5.2))
    fig.patch.set_facecolor(BG)
    ax.set_facecolor(BG)

    day_numbers = list(range(1, last_day + 1))
    colors = [
        _day_bar_color(
            day_entries[i],
            highlight=bool(highlight and day == highlight),
        )
        for i, day in enumerate(all_days)
    ]

    ax.set_ylabel("Время (часы)", fontsize=11, color=MUTED)
    ax.set_xlim(0.2, last_day + 0.8)
    ax.set_ylim(0, max(Y_MAX_DEFAULT, max_value * 1.15))
    _style_calm_axes(ax)
    ax.axhline(
        GOAL_HOURS,
        color=GOAL_LINE_COLOR,
        linewidth=1.2,
        solid_capstyle="round",
        zorder=2,
    )

    for day_num, entry, color in zip(day_numbers, day_entries, colors):
        if entry.is_rest:
            _draw_rest_marker(ax, day_num, 0.72, PRODUCTIVE_COLOR)
            continue
        if not _day_is_marked(entry):
            ax.bar(
                day_num,
                0.12,
                width=0.55,
                color=EMPTY_COLOR,
                edgecolor="none",
                zorder=2,
                alpha=0.5,
            )
            continue
        height = entry.hours if entry.hours > 0 else REST_MARKER_HEIGHT
        ax.bar(
            day_num,
            height,
            width=0.62,
            color=color,
            edgecolor="none",
            zorder=3,
            alpha=0.95,
        )
        if entry.is_breakthrough:
            _annotate_breakthrough(ax, day_num, height, color)

    _apply_day_axis_labels(ax, all_days)

    fig.text(
        0.5,
        0.94,
        title,
        ha="center",
        va="top",
        fontsize=14,
        fontweight="semibold",
        color=INK,
    )
    month_total = (
        f"Итого: {format_duration(total_month)}"
        if total_month > 0
        else "Итого: 0ч"
    )
    fig.text(0.5, 0.885, month_total, ha="center", va="top", fontsize=11, color=MUTED)

    buf = io.BytesIO()
    fig.subplots_adjust(left=0.05, right=0.985, top=0.80, bottom=0.14)
    fig.savefig(buf, format="png", dpi=160, facecolor=fig.get_facecolor())
    plt.close(fig)
    buf.seek(0)
    return buf.read()


def _render_team_chart(
    users_series: list[tuple[str, dict[dt.date, DayEntry]]],
    title: str,
    year: int,
    month: int,
) -> bytes:
    _, last_day = calendar.monthrange(year, month)
    all_days = [dt.date(year, month, day) for day in range(1, last_day + 1)]
    day_numbers = np.arange(1, last_day + 1)

    fig, ax = plt.subplots(figsize=(max(14.0, last_day * 0.5), 5.2))
    fig.patch.set_facecolor(BG)
    ax.set_facecolor(BG)

    group_width = 0.72
    max_value = 0.0
    for day in all_days:
        for _name, entries in users_series:
            entry = _entry_for_day(entries, day)
            if entry.hours > 0 and not entry.is_rest:
                max_value = max(max_value, entry.hours)

    ax.set_ylabel("Время (часы)", fontsize=11, color=MUTED, labelpad=8)
    ax.set_xlim(0.2, last_day + 0.8)
    ax.set_ylim(0, max(Y_MAX_DEFAULT, max_value * 1.15))
    _style_calm_axes(ax)
    ax.axhline(
        GOAL_HOURS,
        color=GOAL_LINE_COLOR,
        linewidth=1.3,
        solid_capstyle="round",
        zorder=2,
    )

    for day_num, day in zip(day_numbers, all_days):
        marked: list[tuple[int, DayEntry]] = []
        for idx, (_name, entries) in enumerate(users_series):
            entry = _entry_for_day(entries, day)
            if _day_is_marked(entry):
                marked.append((idx, entry))

        if not marked:
            continue

        bar_width = group_width / len(marked)
        for slot, (idx, entry) in enumerate(marked):
            offset = (slot - (len(marked) - 1) / 2) * bar_width
            x = float(day_num + offset)
            base_color = USER_COLORS[idx % len(USER_COLORS)]

            if entry.is_rest:
                _draw_rest_marker(ax, x, bar_width, base_color)
                continue

            height = entry.hours if entry.hours > 0 else REST_MARKER_HEIGHT
            ax.bar(
                x,
                height,
                width=bar_width * 0.85,
                color=base_color,
                edgecolor="none",
                zorder=3,
                alpha=0.95,
            )
            if entry.is_breakthrough:
                _annotate_breakthrough(ax, x, height, base_color)

    _apply_day_axis_labels(ax, all_days)

    fig.text(
        0.5,
        0.94,
        title,
        ha="center",
        va="top",
        fontsize=15,
        fontweight="semibold",
        color=INK,
    )

    totals = [
        (
            name,
            idx,
            _month_total_hours(entries, all_days),
        )
        for idx, (name, entries) in enumerate(users_series)
    ]
    n = len(totals)
    for i, (name, idx, total_h) in enumerate(totals):
        x = 0.08 + (i + 0.5) * (0.84 / n) if n else 0.5
        fig.text(
            x,
            0.875,
            f"{name}: {format_duration(total_h)}",
            ha="center",
            va="top",
            fontsize=11,
            fontweight="medium",
            color=USER_COLORS[idx % len(USER_COLORS)],
        )

    buf = io.BytesIO()
    fig.subplots_adjust(left=0.05, right=0.985, top=0.78, bottom=0.14)
    fig.savefig(buf, format="png", dpi=160, facecolor=fig.get_facecolor())
    plt.close(fig)
    buf.seek(0)
    return buf.read()


def _draw_month_breakthrough_calendar(
    ax,
    year: int,
    month: int,
    users_series: list[tuple[str, str, set[dt.date]]],
) -> None:
    ax.set_xlim(0, 7)
    ax.set_ylim(0, 7)
    ax.invert_yaxis()
    ax.axis("off")
    ax.set_title(MONTH_NAMES[month], fontsize=14, fontweight="bold", pad=8, color=INK)

    for col, abbr in enumerate(WEEKDAY_ABBR):
        wd_color = WEEKEND_LABEL_COLOR if col >= 5 else MUTED
        ax.text(
            col + 0.5,
            0.35,
            abbr,
            ha="center",
            va="center",
            fontsize=9,
            fontweight="bold",
            color=wd_color,
        )

    cal = calendar.Calendar(firstweekday=0)
    for week_idx, week in enumerate(cal.monthdayscalendar(year, month)):
        for col, day in enumerate(week):
            if day == 0:
                continue
            row = week_idx + 1
            day_date = dt.date(year, month, day)
            marked = [
                (name, color)
                for name, color, dates in users_series
                if day_date in dates
            ]

            ax.add_patch(
                Rectangle(
                    (col, row),
                    1,
                    1,
                    facecolor=BREAKTHROUGH_CELL_COLOR if marked else "#FFFFFF",
                    edgecolor=GRID,
                    linewidth=1.0,
                )
            )

            day_color = WEEKEND_LABEL_COLOR if col >= 5 else INK
            ax.text(
                col + 0.5,
                row + 0.38,
                str(day),
                ha="center",
                va="center",
                fontsize=11,
                fontweight="bold",
                color=day_color,
            )

            for star_idx, (_name, color) in enumerate(marked):
                offset = (star_idx - (len(marked) - 1) / 2) * 0.24
                ax.text(
                    col + 0.5 + offset,
                    row + 0.72,
                    "★",
                    ha="center",
                    va="center",
                    fontsize=10,
                    fontweight="bold",
                    color=color,
                )


def _render_year_breakthrough_calendar(
    year: int,
    users_series: list[tuple[str, str, set[dt.date]]],
) -> bytes:
    fig, axes = plt.subplots(4, 3, figsize=(22, 28))
    fig.patch.set_facecolor(BG)

    total_days = sum(len(dates) for _n, _c, dates in users_series)
    fig.suptitle(
        f"Календарь прорывных дней — {year}",
        fontsize=22,
        fontweight="bold",
        y=0.985,
        color=INK,
    )

    for month in range(1, 13):
        ax = axes[(month - 1) // 3, (month - 1) % 3]
        ax.set_facecolor(BG)
        _draw_month_breakthrough_calendar(ax, year, month, users_series)

    if users_series:
        legend_handles = [
            Patch(facecolor=color, edgecolor=color, label=name)
            for name, color, _dates in users_series
            if _dates
        ]
        if not legend_handles:
            legend_handles = [
                Patch(facecolor=color, edgecolor=color, label=name)
                for name, color, _dates in users_series
            ]
        fig.legend(
            handles=legend_handles,
            loc="lower center",
            ncol=min(len(legend_handles), 3),
            fontsize=12,
            framealpha=0.9,
            bbox_to_anchor=(0.5, 0.015),
        )
    else:
        fig.text(
            0.5,
            0.02,
            "Прорывных дней за год пока нет",
            ha="center",
            fontsize=13,
            color=MUTED,
        )

    subtitle = (
        f"Всего прорывных дней: {total_days}"
        if total_days
        else "Отметьте прорыв через «✅отметить» — слово «прорыв»"
    )
    fig.text(0.5, 0.045, subtitle, ha="center", fontsize=12, color=MUTED)

    buf = io.BytesIO()
    plt.tight_layout(rect=[0, 0.07, 1, 0.965], h_pad=2.8, w_pad=1.8)
    fig.savefig(buf, format="png", dpi=150, facecolor=fig.get_facecolor())
    plt.close(fig)
    buf.seek(0)
    return buf.read()


async def _load_users_breakthrough_series(
    year: int,
) -> list[tuple[str, str, set[dt.date]]]:
    users = await get_registered_users()
    dates_by_user: dict[int, set[dt.date]] = {uid: set() for uid, _ in users}

    for user_id, _name, entry_date, _note in await get_breakthroughs_for_year(year):
        if user_id in dates_by_user:
            dates_by_user[user_id].add(entry_date)

    series: list[tuple[str, str, set[dt.date]]] = []
    for idx, (user_id, name) in enumerate(users):
        display = await get_display_name(user_id) or name
        dates = dates_by_user.get(user_id, set())
        color = USER_COLORS[idx % len(USER_COLORS)]
        series.append((display, color, dates))
    return series


async def build_breakthrough_year_calendar(year: int) -> tuple[bytes, str]:
    users_series = await _load_users_breakthrough_series(year)
    png = await asyncio.to_thread(
        _render_year_breakthrough_calendar, year, users_series
    )
    total = sum(len(dates) for _n, _c, dates in users_series)
    caption = f"⭐ <b>Календарь прорывов</b> · {year} · дней: <b>{total}</b>"
    return png, caption


async def _load_users_month_data(
    year: int, month: int,
) -> list[tuple[int, str, dict[dt.date, DayEntry]]]:
    result: list[tuple[int, str, dict[dt.date, DayEntry]]] = []
    for user_id, name in await get_registered_users():
        display = await get_display_name(user_id) or name
        await fill_missed_days_for_month(user_id, display, year, month)
        entries = await get_month_entries(user_id, year, month)
        result.append((user_id, display, entries))
    return result


async def build_team_progress_chart(year: int, month: int) -> tuple[bytes, str]:
    users_data = await _load_users_month_data(year, month)
    if not users_data:
        raise RuntimeError("Нет зарегистрированных участников")

    users_series = [(name, entries) for _, name, entries in users_data]
    title = f"Общий прогресс — {MONTH_NAMES[month]} {year}"
    png = await asyncio.to_thread(
        _render_team_chart, users_series, title, year, month
    )
    caption = f"📊 <b>Общий график</b> · {MONTH_NAMES[month]} {year}"
    return png, caption


async def build_progress_chart(
    user_id: int,
    year: int,
    month: int,
    *,
    highlight: dt.date | None = None,
) -> tuple[bytes, str]:
    """Один участник — для обратной совместимости."""
    name = await get_display_name(user_id) or f"ID {user_id}"
    await fill_missed_days_for_month(user_id, name, year, month)
    entries = await get_month_entries(user_id, year, month)
    title = f"{name} — {MONTH_NAMES[month]} {year}"
    png = await asyncio.to_thread(
        _render_single_chart, entries, title, year, month, highlight
    )

    if highlight and highlight in entries:
        day_label = highlight.strftime("%d.%m.%Y")
        entry = entries[highlight]
        if entry.is_rest:
            day_info = "<b>день отдыха</b>"
        elif entry.is_breakthrough:
            if entry.hours > 0:
                day_info = (
                    f"<b>день прорыва</b> ⭐ · <b>{format_duration(entry.hours)}</b> "
                    f"(<code>{format_duration_clock(entry.hours)}</code>)"
                )
            else:
                day_info = "<b>день прорыва</b> ⭐"
        else:
            day_info = (
                f"<b>{format_duration(entry.hours)}</b> "
                f"(<code>{format_duration_clock(entry.hours)}</code>)"
            )
        caption = (
            f"📊 <b>{name}</b> · {MONTH_NAMES[month]} {year}\n"
            f"Отмечено {day_label}: {day_info}"
        )
    else:
        caption = f"📊 <b>{name}</b> · {MONTH_NAMES[month]} {year}"

    return png, caption


def chart_photo(png: bytes, filename: str = "progress.png") -> BufferedInputFile:
    from aiogram.types import BufferedInputFile

    return BufferedInputFile(png, filename=filename)
