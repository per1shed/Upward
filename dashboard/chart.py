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
        n_users = max(len(metrics.users), 1)
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
        bar_w = group_w / n_users
        labels: list[tuple[float, float, str, str]] = []

        for day in range(1, last + 1):
            di = day - 1
            for ui, user in enumerate(metrics.users):
                x = day - group_w / 2 + bar_w * (ui + 0.5)
                hours = user.daily_hours[di]
                is_rest = user.daily_rest[di]
                is_br = user.daily_breakthrough[di]

                if is_rest:
                    height = max(0.45, y_top * 0.08)
                    ax.bar(
                        x,
                        height,
                        width=bar_w * 0.78,
                        facecolor="none",
                        edgecolor=user.color,
                        linewidth=t.rest_linewidth,
                        zorder=3,
                    )
                    continue

                if hours <= 0 and not is_br:
                    continue

                height = hours if hours > 0 else max(0.35, y_top * 0.06)
                ax.bar(
                    x,
                    height,
                    width=bar_w * 0.78,
                    color=user.color,
                    edgecolor="none",
                    zorder=3,
                    alpha=0.95,
                )
                if is_br:
                    ax.text(
                        x,
                        height + y_top * 0.015,
                        "★",
                        ha="center",
                        va="bottom",
                        fontsize=8,
                        color=user.color,
                        fontweight="bold",
                        zorder=5,
                    )
                if hours > 0:
                    labels.append(
                        (
                            x,
                            height,
                            format_duration_clock(hours),
                            user.color,
                        )
                    )

        self._place_labels(ax, labels, y_top)

        ax.set_xlim(0.4, last + 0.6)
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
        labels: list[tuple[float, float, str, str]],
        y_top: float,
    ) -> None:
        """Avoid overlaps: nudge labels up when neighbors are close."""
        t = self.theme
        if not labels:
            return
        # Sort by x then height
        items = sorted(labels, key=lambda r: (r[0], -r[1]))
        placed: list[tuple[float, float]] = []  # (x, y_text)
        min_dx = 0.32
        min_dy = y_top * 0.045

        for x, height, text, color in items:
            y = height + y_top * 0.018
            # Star may sit near breakthrough labels — small extra pad if crowded
            for px, py in placed:
                if abs(px - x) < min_dx and abs(py - y) < min_dy:
                    y = max(y, py + min_dy)
            y = min(y, y_top * 0.97)
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
            placed.append((x, y))
