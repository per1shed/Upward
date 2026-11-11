"""Графики финансов, состояния и трафика — те же правила, что в веб-приложении."""
from __future__ import annotations

import calendar
import datetime as dt
import io

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import FancyBboxPatch

BG = "#F7F7F8"
INK = "#1D1D1F"
MUTED = "#8E8E93"
GRID = "#E4E4E8"
WEEKEND = "#EEF0F4"

CASH = "#34C759"
DEBT = "#FF453A"
BALANCE = "#0A84FF"
PHYSICAL = "#0A84FF"
MORAL = "#BF5AF2"
TRAFFIC = "#FF9F0A"


def _png(fig) -> bytes:
    buffer = io.BytesIO()
    fig.savefig(buffer, format="png", dpi=160, bbox_inches="tight", facecolor=BG)
    plt.close(fig)
    return buffer.getvalue()


def _line_bounds(values: list[float]) -> tuple[float, float]:
    lo = min(values)
    hi = max(values)
    if not hi > lo:
        pad = max(abs(lo) * 0.08, 1)
        lo -= pad
        hi += pad
    span = hi - lo
    if lo > 0 and lo <= span * 0.45:
        lo = 0
    if hi < 0 and -hi <= span * 0.45:
        hi = 0
    if not hi > lo:
        hi = lo + 1
    return lo, hi


def _known(points: list[float | None]) -> list[tuple[int, float]]:
    return [(index, float(value)) for index, value in enumerate(points) if value is not None]


def _weekend_bands(ax, count: int, year: int, month: int) -> None:
    for day in range(1, count + 1):
        if dt.date(year, month, day).weekday() >= 5:
            ax.axvspan(day - 1.5, day - 0.5, color=WEEKEND, zorder=0)


def _style(ax, title: str) -> None:
    ax.set_facecolor(BG)
    if title:
        ax.set_title(title, loc="left", color=INK, fontsize=13, pad=8)
    ax.tick_params(colors=MUTED, labelsize=8)
    ax.grid(axis="y", linestyle=":", linewidth=0.8, color=GRID, zorder=0)
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.set_axisbelow(True)


def _day_ticks(ax, count: int) -> None:
    ticks = list(range(1, count + 1, 2 if count > 16 else 1))
    ax.set_xticks([day - 1 for day in ticks])
    ax.set_xticklabels([str(day) for day in ticks])
    ax.set_xlim(-0.6, count - 0.4)


def _fill_under(ax, xs: list[float], ys: list[float], lo: float, wash: str | tuple[str, str]) -> None:
    if isinstance(wash, str):
        ax.fill_between(xs, ys, lo, color=wash, alpha=0.28, zorder=2)
        return
    positive, negative = wash
    count = len(xs)
    for index in range(count):
        color = positive if ys[index] >= 0 else negative
        poly_x = [xs[index]]
        poly_y = [ys[index]]
        if index > 0:
            poly_x.insert(0, (xs[index - 1] + xs[index]) / 2)
            poly_y.insert(0, (ys[index - 1] + ys[index]) / 2)
        if index < count - 1:
            poly_x.append((xs[index] + xs[index + 1]) / 2)
            poly_y.append((ys[index] + ys[index + 1]) / 2)
        if len(poly_x) < 2:
            continue
        ax.fill_between(poly_x, poly_y, lo, color=color, alpha=0.28, zorder=2, linewidth=0)


def render_lines(
    panels: list[tuple[str, list[float | None], str, str | tuple[str, str]]],
    *,
    year: int,
    month: int,
) -> bytes:
    count = calendar.monthrange(year, month)[1]
    fig, axes = plt.subplots(len(panels), 1, figsize=(8.4, 2.35 * len(panels)), facecolor=BG)
    if len(panels) == 1:
        axes = [axes]
    x = np.arange(count)
    for ax, (title, points, color, wash) in zip(axes, panels):
        _style(ax, title)
        _weekend_bands(ax, count, year, month)
        known = _known(points)
        if len(known) >= 2:
            xs = [index for index, _value in known]
            ys = [value for _index, value in known]
            lo, hi = _line_bounds(ys)
            _fill_under(ax, xs, ys, lo, wash)
            ax.plot(xs, ys, color=color, linewidth=2.2, solid_capstyle="round", zorder=3)
            ax.set_ylim(lo, hi + (hi - lo) * 0.08)
        elif len(known) == 1:
            ax.scatter([known[0][0]], [known[0][1]], color=color, s=28, zorder=3)
        _day_ticks(ax, count)
    fig.tight_layout(pad=0.6)
    return _png(fig)


def _axis_money(value: float, _pos: int) -> str:
    number = int(round(value))
    sign = "−" if number < 0 else ""
    return sign + f"{abs(number):,}".replace(",", " ")


def _toward_zero(value: float, others: list[float]) -> float:
    if value > 0:
        between = [item for item in others if 0 <= item < value]
        return max(between) if between else 0.0
    if value < 0:
        between = [item for item in others if value < item <= 0]
        return min(between) if between else 0.0
    return 0.0


def _glow_to_zero(ax, tracks: list[tuple[str, np.ndarray, np.ndarray]]) -> None:
    """Свечение каждой линии только до соседней метрики или до нуля."""
    if len(tracks) < 1:
        return
    left = min(float(xs[0]) for _color, xs, _ys in tracks)
    right = max(float(xs[-1]) for _color, xs, _ys in tracks)
    grid = np.linspace(left, right, max(int((right - left) * 32), 2))
    sampled: list[tuple[str, np.ndarray, np.ndarray]] = []
    for color, xs, ys in tracks:
        inside = (grid >= xs[0]) & (grid <= xs[-1])
        sampled.append((color, np.interp(grid, xs, ys), inside))
    for index, (color, values, inside) in enumerate(sampled):
        edge = np.array(
            [
                _toward_zero(
                    float(value),
                    [
                        float(other[point])
                        for other_index, (_other_color, other, other_inside) in enumerate(sampled)
                        if other_index != index and other_inside[point]
                    ],
                )
                if inside[point]
                else float(value)
                for point, value in enumerate(values)
            ]
        )
        ax.fill_between(grid, values, edge, where=inside, color=color, alpha=0.22, linewidth=0, zorder=2)


def _segments(points: list[float | None]) -> list[tuple[np.ndarray, np.ndarray]]:
    segments: list[tuple[np.ndarray, np.ndarray]] = []
    xs: list[float] = []
    ys: list[float] = []
    previous: int | None = None
    for index, value in enumerate(points):
        gap = previous is not None and index != previous + 1
        if (value is None or gap) and xs:
            segments.append((np.array(xs, dtype=float), np.array(ys, dtype=float)))
            xs, ys = [], []
        if value is None:
            previous = None
            continue
        xs.append(float(index))
        ys.append(float(value))
        previous = index
    if xs:
        segments.append((np.array(xs, dtype=float), np.array(ys, dtype=float)))
    return segments


def render_finance(
    series: list[tuple[str, list[float | None], str]],
    *,
    year: int,
    month: int,
) -> bytes:
    count = calendar.monthrange(year, month)[1]
    fig, ax = plt.subplots(figsize=(8.4, 4.6), facecolor=BG)
    _style(ax, "")
    _weekend_bands(ax, count, year, month)
    prepared = [(title, points, color) for title, points, color in series]
    values = [float(value) for _title, points, _color in prepared for value in points if value is not None]
    if values:
        lo, hi = _line_bounds(values)
        if lo > 0:
            lo = 0
        if hi < 0:
            hi = 0
        span = max(hi - lo, 1)
        ax.set_ylim(lo, hi + span * 0.08)
        if lo < 0 < hi or lo == 0 or hi == 0:
            ax.axhline(0, color=MUTED, linewidth=0.8, alpha=0.45, zorder=2.5)
    tracks = []
    for _title, points, color in prepared:
        for xs, ys in _segments(points):
            if len(xs) < 2:
                continue
            tracks.append((color, xs, ys))
    _glow_to_zero(ax, tracks)
    ax.yaxis.set_major_formatter(plt.FuncFormatter(_axis_money))
    handles = []
    seen: set[str] = set()
    for title, points, color in reversed(prepared):
        labeled = False
        for xs, ys in _segments(points):
            label = title if title not in seen else None
            if len(xs) >= 2:
                line, = ax.plot(xs, ys, color=color, linewidth=2.2, solid_capstyle="round", zorder=3, label=label)
            else:
                line, = ax.plot(
                    xs,
                    ys,
                    color=color,
                    marker="o",
                    markersize=5,
                    linewidth=0,
                    zorder=3,
                    label=label,
                )
            if label:
                handles.append(line)
                seen.add(title)
                labeled = True
        if not labeled and title in seen:
            continue
    handles.reverse()
    if handles:
        legend = ax.legend(
            handles=handles,
            loc="lower left",
            bbox_to_anchor=(0.0, 1.02),
            ncol=len(handles),
            frameon=False,
            fontsize=11,
            handlelength=1.6,
            columnspacing=1.4,
            borderaxespad=0.0,
        )
        for text, handle in zip(legend.get_texts(), handles):
            text.set_color(handle.get_color())
    _day_ticks(ax, count)
    fig.tight_layout(pad=0.6)
    return _png(fig)


def render_bars(
    panels: list[tuple[str, list[float | None], str]],
    *,
    year: int,
    month: int,
    scale: float | None = None,
) -> bytes:
    count = calendar.monthrange(year, month)[1]
    fig, axes = plt.subplots(len(panels), 1, figsize=(8.4, 2.35 * len(panels)), facecolor=BG)
    if len(panels) == 1:
        axes = [axes]
    for ax, (title, points, color) in zip(axes, panels):
        _style(ax, title)
        _weekend_bands(ax, count, year, month)
        heights = []
        positions = []
        top = 1.0
        for index, value in enumerate(points):
            if value is None or not value > 0:
                continue
            heights.append(value)
            positions.append(index)
            top = max(top, value)
        if heights:
            ax.bar(positions, heights, width=0.62, color=color, zorder=3)
        if scale is not None:
            ax.set_ylim(0, scale)
            ax.set_yticks(list(range(0, int(scale) + 1)))
        else:
            if any((value or 0) > 1 for value in points):
                top = float(np.ceil(top))
            ax.set_ylim(0, max(top, 1) * 1.12)
        _day_ticks(ax, count)
    fig.tight_layout(pad=0.6)
    return _png(fig)


PLAN_COLORS = {
    "Утренняя рутина": "#FFD60A",
    "Зал": "#64D2FF",
    "Бизнес": "#FF9F0A",
    "IT": "#30D158",
    "Университет": "#A82432",
    "Вечерняя рутина": "#3B82F6",
    "Сон": "#7B6BB0",
    "Отдых": "#5B8DEF",
}
_WEEKDAYS = ("понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье")
_MONTHS = (
    "",
    "января",
    "февраля",
    "марта",
    "апреля",
    "мая",
    "июня",
    "июля",
    "августа",
    "сентября",
    "октября",
    "ноября",
    "декабря",
)


def _ink(color: str) -> str:
    red = int(color[1:3], 16)
    green = int(color[3:5], 16)
    blue = int(color[5:7], 16)
    bright = (0.299 * red + 0.587 * green + 0.114 * blue) / 255
    return INK if bright > 0.62 else "#FFFFFF"


def _clock(minutes: int) -> str:
    return f"{(minutes // 60) % 24:02d}:{minutes % 60:02d}"


def render_plan(blocks: list[dict], moment: dt.datetime, mode: str, current: dict | None) -> bytes:
    count = max(len(blocks), 1)
    fig_h = 1.15 + count * 0.62
    fig, ax = plt.subplots(figsize=(7.4, fig_h), facecolor=BG)
    ax.set_xlim(0, 10)
    ax.set_ylim(0, count)
    ax.axis("off")
    ax.set_facecolor(BG)
    date_line = f"{_WEEKDAYS[moment.weekday()]}, {moment.day} {_MONTHS[moment.month]}"
    now_line = f"Сейчас · {current['title']}" if current else "Сейчас · —"
    fig.text(0.06, 0.965, date_line, color=INK, fontsize=15, fontweight="medium", va="top")
    fig.text(0.06, 0.905, f"{now_line} · {mode}", color=MUTED, fontsize=11, va="top")
    current_start = current.get("start") if current else None
    current_title = current.get("title") if current else None
    for index, block in enumerate(blocks):
        y = count - index - 1
        color = PLAN_COLORS.get(block["title"], "#8E8E93")
        active = block["start"] == current_start and block["title"] == current_title
        patch = FancyBboxPatch(
            (0.15, y + 0.1),
            9.7,
            0.8,
            boxstyle="round,pad=0.02,rounding_size=0.18",
            facecolor=color,
            edgecolor="#FFFFFF" if active else color,
            linewidth=2.4 if active else 0,
            mutation_aspect=0.35,
        )
        ax.add_patch(patch)
        tone = _ink(color)
        ax.text(0.45, y + 0.5, f"{_clock(block['start'])}–{_clock(block['end'])}", va="center", ha="left", color=tone, fontsize=12)
        ax.text(3.55, y + 0.5, block["title"], va="center", ha="left", color=tone, fontsize=13, fontweight="medium")
        if active:
            ax.text(9.55, y + 0.5, "сейчас", va="center", ha="right", color=tone, fontsize=11)
    fig.subplots_adjust(left=0.02, right=0.98, top=0.84, bottom=0.03)
    return _png(fig)
