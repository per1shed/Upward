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
    fig.savefig(buffer, format="png", dpi=160, bbox_inches="tight", facecolor=fig.get_facecolor())
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


def finance_lines(
    cash: list[float | None],
    debt: list[float | None],
    balance: list[float | None],
) -> tuple[list[float | None], list[float | None], list[float | None]]:
    """Синяя линия есть, пока долги больше нуля, и не поднимается выше них."""
    money: list[float | None] = []
    debts: list[float | None] = []
    net: list[float | None] = []
    debt_drawn = False
    debt_closed = False
    for cash_value, debt_value, balance_value in zip(cash, debt, balance):
        if cash_value is None and debt_value is None and balance_value is None:
            money.append(None)
            debts.append(None)
            net.append(None)
            continue
        if debt_value in (None, 0):
            if debt_drawn and not debt_closed:
                debts.append(0.0)
                net.append(0.0)
                debt_closed = True
            else:
                debts.append(None)
                net.append(None)
            if cash_value is not None:
                money.append(cash_value)
            elif balance_value is not None:
                money.append(balance_value)
            else:
                money.append(None)
            continue
        debt_drawn = True
        debt_closed = False
        money.append(cash_value)
        debts.append(debt_value)
        if balance_value is not None and balance_value > debt_value:
            net.append(debt_value)
        else:
            net.append(balance_value)
    return money, debts, net


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


MONTHS_TITLE = (
    "",
    "Январь",
    "Февраль",
    "Март",
    "Апрель",
    "Май",
    "Июнь",
    "Июль",
    "Август",
    "Сентябрь",
    "Октябрь",
    "Ноябрь",
    "Декабрь",
)
WEEKDAYS = ("Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс")
CARD = "#F5F5F7"


def _pad_month(points: list[float | None], count: int) -> list[float | None]:
    data = list(points)
    if len(data) < count:
        data.extend([None] * (count - len(data)))
    return data[:count]


def _last_value(points: list[float | None]) -> float | None:
    for value in reversed(points):
        if value is not None:
            return float(value)
    return None


def _ruble(value: float | None) -> str:
    if value is None:
        return "—"
    number = int(round(value))
    sign = "−" if number < 0 else ""
    return sign + f"{abs(number):,}".replace(",", " ") + " ₽"


def _axis_compact(value: float, _pos: int) -> str:
    number = int(round(value))
    sign = "−" if number < 0 else ""
    magnitude = abs(number)
    if magnitude >= 1000:
        thousands = magnitude / 1000
        text = f"{thousands:.0f}k" if abs(thousands - round(thousands)) < 0.05 else f"{thousands:.1f}k"
    else:
        text = f"{magnitude:,}".replace(",", " ")
    return sign + text


def _money_vertices(
    money: list[float | None],
    debt: list[float | None],
    balance: list[float | None],
) -> list[list[tuple[float, float]]]:
    """Деньги идут до первого пересечения с долгом или балансом и там обрываются."""
    segments: list[list[tuple[float, float]]] = []
    current: list[tuple[float, float]] = []
    previous: int | None = None
    for index, value in enumerate(money):
        gap = previous is not None and index != previous + 1
        if value is None or gap:
            if current:
                segments.append(current)
                current = []
        if value is None:
            previous = None
            continue
        current.append((float(index), float(value)))
        previous = index
    if current:
        segments.append(current)
    if not segments:
        return segments
    last = segments[-1]
    last_index = int(last[-1][0])
    level = last[-1][1]
    nxt = last_index + 1
    if nxt >= len(money) or money[nxt] is not None:
        return segments
    crossings: list[float] = []
    for series in (debt, balance):
        if nxt >= len(series):
            continue
        start = series[last_index] if last_index < len(series) else None
        end = series[nxt]
        if start is None or end is None or end == start:
            continue
        if (start - level) * (end - level) > 0:
            continue
        share = (level - start) / (end - start)
        if 0 < share <= 1:
            crossings.append(share)
    if crossings:
        last.append((last_index + min(crossings), level))
    return segments


def _snapshot(
    money: list[float | None],
    debt: list[float | None],
    balance: list[float | None],
) -> tuple[float | None, float | None, float | None]:
    """Один день: баланс с учётом долгов всегда равен балансу минус долги."""
    count = max(len(money), len(debt), len(balance))
    for index in range(count - 1, -1, -1):
        cash_value = money[index] if index < len(money) else None
        debt_value = debt[index] if index < len(debt) else None
        balance_value = balance[index] if index < len(balance) else None
        if cash_value is None and debt_value is None and balance_value is None:
            continue
        if cash_value is not None:
            owed = 0.0 if debt_value in (None, 0) else float(debt_value)
            return float(cash_value), owed, float(cash_value) - owed
        if balance_value is None:
            continue
        owed = 0.0 if debt_value in (None, 0) else float(debt_value)
        return float(balance_value) + owed, owed, float(balance_value)
    return None, None, None


def _metric_cards(fig, cash: list[float | None], debt: list[float | None], balance: list[float | None]) -> None:
    cash_now, debt_now, net_now = _snapshot(cash, debt, balance)
    specs = (
        (CASH, "Баланс", cash_now),
        (DEBT, "Долги", debt_now),
        (BALANCE, "Баланс с учётом долгов", net_now),
    )
    gap = 0.018
    left = 0.045
    width = (0.91 - 2 * gap) / 3
    for index, (color, title, value) in enumerate(specs):
        card = fig.add_axes([left + index * (width + gap), 0.735, width, 0.12])
        card.set_xlim(0, 1)
        card.set_ylim(0, 1)
        card.axis("off")
        card.add_patch(
            FancyBboxPatch(
                (0.0, 0.02),
                1.0,
                0.96,
                boxstyle="round,pad=0.008,rounding_size=0.06",
                facecolor=CARD,
                edgecolor="#EEEEF0",
                linewidth=0.8,
                mutation_aspect=0.28,
                transform=card.transAxes,
            )
        )
        card.add_patch(
            plt.Rectangle((0.04, 0.24), 0.015, 0.52, color=color, transform=card.transAxes, linewidth=0, zorder=3)
        )
        card.text(0.09, 0.66, title, color=MUTED, fontsize=8.5, va="center", ha="left", transform=card.transAxes)
        card.text(
            0.09,
            0.32,
            _ruble(value),
            color=INK,
            fontsize=13,
            fontweight="bold",
            va="center",
            ha="left",
            transform=card.transAxes,
        )


def _finance_days(ax, count: int, year: int, month: int) -> None:
    ax.set_xticks(list(range(count)))
    labels = []
    weekend = []
    for day in range(1, count + 1):
        stamp = dt.date(year, month, day)
        labels.append(f"{day}\n{WEEKDAYS[stamp.weekday()]}")
        weekend.append(stamp.weekday() >= 5)
        if stamp.weekday() >= 5:
            ax.axvspan(day - 1.5, day - 0.5, color="#F2F2F6", zorder=0)
    ax.set_xticklabels(labels, fontsize=6.2)
    for label, is_weekend in zip(ax.get_xticklabels(), weekend):
        label.set_color("#FF3B30" if is_weekend else MUTED)
    ax.set_xlim(-0.6, count - 0.4)
    ax.tick_params(axis="x", length=0, pad=2)


def render_finance(
    series: list[tuple[str, list[float | None], str]],
    *,
    year: int,
    month: int,
) -> bytes:
    count = calendar.monthrange(year, month)[1]
    prepared = [(title, _pad_month(points, count), color) for title, points, color in series]
    by_color = {color: points for _title, points, color in prepared}
    money = by_color.get(CASH, [None] * count)
    debt = by_color.get(DEBT, [None] * count)
    balance = by_color.get(BALANCE, [None] * count)
    fig = plt.figure(figsize=(10.4, 6.5), facecolor="white")
    fig.text(0.045, 0.955, "Финансы", fontsize=18, fontweight="bold", color=INK, ha="left", va="top")
    fig.text(0.045, 0.905, f"{MONTHS_TITLE[month]} {year}", fontsize=12, color=MUTED, ha="left", va="top")
    _metric_cards(fig, money, debt, balance)
    ax = fig.add_axes([0.055, 0.08, 0.90, 0.62])
    ax.set_facecolor("white")
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.grid(axis="y", linestyle=":", linewidth=0.7, color=GRID, zorder=0)
    ax.tick_params(axis="y", colors=MUTED, labelsize=9, length=0)
    ax.yaxis.set_major_formatter(plt.FuncFormatter(_axis_compact))
    values = [float(value) for points in (money, debt, balance) for value in points if value is not None]
    money_lines = _money_vertices(money, debt, balance)
    values.extend(point[1] for line in money_lines for point in line)
    if values:
        lo, hi = _line_bounds(values)
        if lo > 0:
            lo = 0.0
        if hi < 0:
            hi = 0.0
        span = max(hi - lo, 1)
        ax.set_ylim(lo - span * 0.06, hi + span * 0.08)
        ax.axhline(0, color="#C7C7CC", linewidth=0.9, linestyle=(0, (3, 3)), zorder=1)
    drawn: list[tuple[np.ndarray, np.ndarray, str]] = []
    for title, points, color in prepared:
        if color == CASH:
            for line in money_lines:
                if len(line) >= 2:
                    xs = np.array([point[0] for point in line], dtype=float)
                    ys = np.array([point[1] for point in line], dtype=float)
                    drawn.append((xs, ys, color))
                elif len(line) == 1:
                    ax.plot(line[0][0], line[0][1], color=color, marker="o", markersize=4.5, zorder=4)
            continue
        for xs, ys in _segments(points):
            if len(xs) >= 2:
                drawn.append((xs, ys, color))
            elif len(xs) == 1:
                ax.plot(xs, ys, color=color, marker="o", markersize=4.5, linewidth=0, zorder=4)
    _glow_to_zero(ax, [(color, xs, ys) for xs, ys, color in drawn if len(xs) >= 2])
    # Долги снизу, баланс с учётом долгов поверх: он доходит до той же точки и не выше.
    for color in (DEBT, BALANCE, CASH):
        for xs, ys, track_color in drawn:
            if track_color != color:
                continue
            ax.plot(xs, ys, color=color, linewidth=1.8, solid_capstyle="round", solid_joinstyle="round", zorder=4)
    _finance_days(ax, count, year, month)
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
