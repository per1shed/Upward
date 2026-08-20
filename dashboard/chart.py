"""Main day-by-day grouped bar chart for the dashboard."""
from __future__ import annotations

import datetime as dt

from time_format import format_duration_clock

from dashboard.metrics import TeamMonthMetrics
from dashboard.theme import WEEKDAY_SHORT, Theme


class ChartRenderer:
    def __init__(self, theme: Theme) -> None:
        self.theme = theme

    def y_top(self, metrics: TeamMonthMetrics) -> float:
        peak = max(
            (h for u in metrics.users for h in u.daily_hours),
            default=0.0,
        )
        if peak <= 0:
            return self.theme.y_min_top
        return max(self.theme.y_min_top, peak + self.theme.y_pad_hours)

    def draw(self, ax, metrics: TeamMonthMetrics) -> None:
        t = self.theme
        ax.set_facecolor(t.card_bg)
        last = metrics.last_day
        y_top = self.y_top(metrics)

        # Weekend bands
        for day in range(1, last + 1):
            d = dt.date(metrics.year, metrics.month, day)
            if d.weekday() >= 5:
                ax.axvspan(
                    day - 0.5,
                    day + 0.5,
                    facecolor=t.weekend_band,
                    edgecolor="none",
                    zorder=0,
                )

        group_w = t.group_width
        labels: list[tuple[float, float, str, str, bool]] = []

        for day in range(1, last + 1):
            di = day - 1
            # Only people who marked this day share the day slot
            marked = []
            for user in metrics.users:
                hours = user.daily_hours[di]
                is_rest = user.daily_rest[di]
                is_br = user.daily_breakthrough[di]
                if is_rest or is_br or hours > 0:
                    marked.append((user, hours, is_rest, is_br))

            if not marked:
                continue

            bar_w = group_w / len(marked)
            for slot, (user, hours, is_rest, is_br) in enumerate(marked):
                x = day - group_w / 2 + bar_w * (slot + 0.5)
                draw_w = bar_w * 0.82

                if is_rest:
                    height = max(0.45, y_top * 0.08)
                    ax.bar(
                        x,
                        height,
                        width=draw_w,
                        facecolor="none",
                        edgecolor=user.color,
                        linewidth=t.rest_linewidth,
                        zorder=3,
                    )
                    continue

                height = hours if hours > 0 else max(0.35, y_top * 0.06)
                ax.bar(
                    x,
                    height,
                    width=draw_w,
                    color=user.color,
                    edgecolor="none",
                    zorder=3,
                    alpha=0.95,
                )
                if hours > 0:
                    labels.append(
                        (
                            x,
                            height,
                            format_duration_clock(hours),
                            user.color,
                            is_br,
                        )
                    )
                elif is_br:
                    # Breakthrough without hours — star alone above the bar
                    labels.append((x, height, "", user.color, True))

        self._place_labels(ax, labels, y_top)

        ax.set_xlim(0.4, last + 0.6)
        # ylim may be expanded inside _place_labels to fit raised captions
        if ax.get_ylim()[1] <= y_top:
            ax.set_ylim(0, y_top)
        ax.set_ylabel("Часы", fontsize=t.axis_size, color=t.muted, labelpad=6)
        ax.tick_params(axis="y", labelsize=t.axis_size, colors=t.muted, length=0)
        ax.tick_params(axis="x", length=0)
        ax.set_xticks(list(range(1, last + 1)))
        ax.set_xticklabels([])

        for day in range(1, last + 1):
            d = dt.date(metrics.year, metrics.month, day)
            color = t.weekend if d.weekday() >= 5 else t.muted
            ax.text(
                day,
                -0.03,
                str(day),
                transform=ax.get_xaxis_transform(),
                ha="center",
                va="top",
                fontsize=t.small_size,
                color=t.ink if d.weekday() < 5 else t.weekend,
                clip_on=False,
            )
            ax.text(
                day,
                -0.075,
                WEEKDAY_SHORT[d.weekday()],
                transform=ax.get_xaxis_transform(),
                ha="center",
                va="top",
                fontsize=t.small_size - 0.5,
                color=color,
                clip_on=False,
            )

        for spine in ("top", "right"):
            ax.spines[spine].set_visible(False)
        ax.spines["left"].set_color(t.border)
        ax.spines["bottom"].set_color(t.border)
        ax.set_axisbelow(True)
        ax.yaxis.grid(True, linestyle="-", linewidth=0.8, color=t.grid)

    def _place_labels(
        self,
        ax,
        labels: list[tuple[float, float, str, str, bool]],
        y_top: float,
    ) -> None:
        """Place H:MM above bars; stack up if they collide with another time label.

        Grid / scale lines may be overlapped — that is fine.
        Overlap with another user's bar column is also allowed.
        """
        t = self.theme
        if not labels:
            ax.set_ylim(0, y_top)
            return

        ax.set_ylim(0, y_top)

        # Tallest bars first so their labels keep the natural position
        items = sorted(labels, key=lambda r: (-r[1], r[0]))
        # (x, y_bottom, y_top_of_glyph) of already placed text
        placed: list[tuple[float, float, float]] = []

        # Generous box so H:MM glyphs don't visually overlap
        label_h = max(y_top * 0.052, 0.42)
        gap = max(y_top * 0.018, 0.12)
        # Same-day grouped bars are ~0.25–0.4 apart — catch them all
        min_dx = 0.58
        time_gap = max(y_top * 0.016, 0.1)
        star_h = label_h * 0.85
        star_gap = label_h * 1.05
        max_y_used = 0.0

        def clear_of_other_labels(x: float, y: float, box_h: float) -> float:
            for _ in range(24):
                y_before = y
                for px, py0, py1 in placed:
                    if abs(px - x) >= min_dx:
                        continue
                    # Vertical ranges overlap (with padding)
                    if y < py1 + gap and (y + box_h) > py0 - gap:
                        y = py1 + gap
                if abs(y - y_before) < 1e-9:
                    break
            return y

        for x, height, text, color, is_br in items:
            y = height + time_gap

            if text:
                y = clear_of_other_labels(x, y, label_h)
                ax.text(
                    x,
                    y,
                    text,
                    ha="center",
                    va="bottom",
                    fontsize=t.bar_label_size,
                    color=color,
                    fontweight="medium",
                    zorder=6,
                    clip_on=False,
                )
                placed.append((x, y, y + label_h))
                max_y_used = max(max_y_used, y + label_h)

            if is_br:
                star_y = (y + star_gap) if text else (height + time_gap)
                star_y = clear_of_other_labels(x, star_y, star_h)
                ax.text(
                    x,
                    star_y,
                    "★",
                    ha="center",
                    va="bottom",
                    fontsize=8,
                    color=color,
                    fontweight="bold",
                    zorder=7,
                    clip_on=False,
                )
                placed.append((x, star_y, star_y + star_h))
                max_y_used = max(max_y_used, star_y + star_h)

        need_top = max(y_top, max_y_used + y_top * 0.05)
        if need_top > y_top:
            ax.set_ylim(0, need_top)
