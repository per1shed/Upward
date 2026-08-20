"""Compose the full Apple-style statistics dashboard PNG."""
from __future__ import annotations

import io
import math

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.gridspec import GridSpec
from matplotlib.patches import Circle, FancyBboxPatch, Wedge

from keyboards import MONTH_NAMES
from time_format import format_duration

from dashboard.chart import ChartRenderer
from dashboard.metrics import MetricsCalculator, TeamMonthMetrics, UserMonthMetrics
from dashboard.theme import Theme


class DashboardRenderer:
    def __init__(self, theme: Theme | None = None) -> None:
        self.theme = theme or Theme()
        self.chart = ChartRenderer(self.theme)

    def render(self, metrics: TeamMonthMetrics) -> bytes:
        t = self.theme
        fig_w = t.width_px / t.dpi
        fig_h = t.height_px / t.dpi
        fig = plt.figure(figsize=(fig_w, fig_h), dpi=t.dpi, facecolor=t.bg)
        plt.rcParams["font.family"] = t.font_family

        show_header = t.show_header
        show_kpi = t.show_kpi_row
        height_ratios: list[float] = []
        if show_header:
            height_ratios.append(0.75)
        if show_kpi:
            height_ratios.append(0.95)
        if t.stacked_mid:
            height_ratios.extend([3.2, 1.35])
        else:
            height_ratios.append(t.height_ratios[0])
        height_ratios.append(t.height_ratios[1])
        if t.leader_own_row:
            height_ratios.append(t.height_ratios[2])
        else:
            # leader sits in the users row — keep users ratio only
            pass

        n_rows = len(height_ratios)
        gs = GridSpec(
            n_rows,
            1,
            figure=fig,
            height_ratios=height_ratios,
            left=t.margin_x,
            right=1 - t.margin_x,
            top=1 - t.margin_y,
            bottom=t.margin_y,
            hspace=t.hspace,
        )

        row = 0
        if show_header:
            self._draw_header(fig, gs[row].subgridspec(1, 1)[0, 0], metrics)
            row += 1
        if show_kpi:
            self._draw_kpi_row(fig, gs[row].subgridspec(1, 3, wspace=0.025), metrics)
            row += 1

        if t.stacked_mid:
            self._draw_main_chart_card(fig, gs[row].subgridspec(1, 1)[0, 0], metrics)
            row += 1
            self._draw_sidebar(fig, gs[row].subgridspec(1, 1)[0, 0], metrics)
            row += 1
        else:
            mid = gs[row].subgridspec(
                1, 2, width_ratios=list(t.mid_width_ratios), wspace=0.03
            )
            self._draw_main_chart_card(fig, mid[0, 0], metrics)
            self._draw_sidebar(fig, mid[0, 1], metrics)
            row += 1

        n_users = max(len(metrics.users), 1)
        if t.leader_own_row:
            users_gs = gs[row].subgridspec(1, n_users, wspace=0.02)
            for i, user in enumerate(metrics.users):
                self._draw_user_card(fig, users_gs[0, i], user, metrics.last_day)
            row += 1
            self._draw_leader_card(fig, gs[row].subgridspec(1, 1)[0, 0], metrics)
        else:
            bottom = gs[row].subgridspec(1, n_users + 1, wspace=0.02)
            for i, user in enumerate(metrics.users):
                self._draw_user_card(fig, bottom[0, i], user, metrics.last_day)
            self._draw_leader_card(fig, bottom[0, -1], metrics)

        if t.layout_label:
            fig.text(
                0.99,
                0.01,
                t.layout_label,
                ha="right",
                va="bottom",
                fontsize=9,
                color=t.muted,
                alpha=0.85,
            )

        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=t.dpi, facecolor=fig.get_facecolor())
        plt.close(fig)
        buf.seek(0)
        return buf.read()

    # --- primitives -----------------------------------------------------

    def _card(self, ax, *, accent: str | None = None) -> None:
        t = self.theme
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        ax.axis("off")
        ax.set_facecolor("none")
        face = accent or t.card_bg
        shadow = FancyBboxPatch(
            (0.012, -0.01),
            0.976,
            0.97,
            boxstyle=f"round,pad=0.01,rounding_size={0.04}",
            linewidth=0,
            facecolor="#000000",
            alpha=t.shadow_alpha,
            transform=ax.transAxes,
            zorder=0,
            clip_on=False,
        )
        card = FancyBboxPatch(
            (0.0, 0.02),
            0.988,
            0.96,
            boxstyle=f"round,pad=0.01,rounding_size={0.04}",
            linewidth=1.0,
            edgecolor=t.border if accent is None else "none",
            facecolor=face,
            transform=ax.transAxes,
            zorder=1,
            clip_on=False,
        )
        ax.add_patch(shadow)
        ax.add_patch(card)

    def _avatar(self, ax, x: float, y: float, user: UserMonthMetrics, r: float = 0.055) -> None:
        # Markers stay circular in screen space (unlike Circle in stretched axes)
        ax.plot(
            [x],
            [y],
            marker="o",
            markersize=r * 220,
            color=user.color,
            markeredgewidth=0,
            zorder=3,
            clip_on=False,
            linestyle="None",
        )
        ax.text(
            x,
            y,
            user.letter,
            ha="center",
            va="center",
            fontsize=self.theme.body_size,
            color="white",
            fontweight="bold",
            zorder=4,
        )

    def _round_icon(
        self, ax, x: float, y: float, *, color: str, glyph: str, size: float = 18
    ) -> None:
        ax.plot(
            [x],
            [y],
            marker="o",
            markersize=size,
            color=color,
            markeredgewidth=0,
            zorder=3,
            clip_on=False,
            linestyle="None",
        )
        ax.text(
            x,
            y,
            glyph,
            ha="center",
            va="center",
            fontsize=max(8, size * 0.45),
            color="white",
            zorder=4,
        )

    # --- sections -------------------------------------------------------

    def _draw_header(self, fig, subplot_spec, metrics: TeamMonthMetrics) -> None:
        t = self.theme
        ax = fig.add_subplot(subplot_spec)
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        ax.axis("off")
        ax.set_facecolor("none")

        month_name = MONTH_NAMES[metrics.month]
        ax.text(
            0.0,
            0.62,
            f"Общий прогресс — {month_name} {metrics.year}",
            ha="left",
            va="center",
            fontsize=t.title_size,
            color=t.ink,
            fontweight="semibold",
        )
        ax.text(
            0.0,
            0.22,
            "Сводка активности участников",
            ha="left",
            va="center",
            fontsize=t.subtitle_size,
            color=t.muted,
        )

        # Month chip (visual only — navigation is Telegram keyboard)
        chip = FancyBboxPatch(
            (0.78, 0.28),
            0.20,
            0.44,
            boxstyle="round,pad=0.01,rounding_size=0.2",
            linewidth=1.0,
            edgecolor=t.border,
            facecolor=t.card_bg,
            transform=ax.transAxes,
            zorder=2,
        )
        ax.add_patch(chip)
        ax.text(
            0.88,
            0.50,
            f"{month_name} {metrics.year}  ▾",
            ha="center",
            va="center",
            fontsize=t.small_size + 1,
            color=t.ink,
            zorder=3,
        )

    def _draw_kpi_row(self, fig, gs_row, metrics: TeamMonthMetrics) -> None:
        t = self.theme
        calc = MetricsCalculator
        # Максимум за день = сумма часов всех, кто отметился в лучший день
        items = [
            ("Всего часов", calc.fmt(metrics.team_total), ""),
            ("Максимум за день", calc.fmt(metrics.daily_max), ""),
            ("Среднее в день", calc.fmt(metrics.avg_day_hours), ""),
        ]
        icons = ("◷", "★", "▮")
        for i, ((label, value, sub), icon) in enumerate(zip(items, icons)):
            ax = fig.add_subplot(gs_row[0, i])
            self._card(ax)
            color = t.kpi_icon_colors[i % len(t.kpi_icon_colors)]
            self._round_icon(ax, 0.12, 0.58, color=color, glyph=icon, size=20)
            ax.text(
                0.28,
                0.68 if sub else 0.58,
                value,
                ha="left",
                va="center",
                fontsize=t.kpi_value_size,
                color=t.ink,
                fontweight="bold",
                zorder=3,
            )
            if sub:
                ax.text(
                    0.28,
                    0.42,
                    sub,
                    ha="left",
                    va="center",
                    fontsize=t.small_size,
                    color=t.muted,
                    zorder=3,
                )
            ax.text(
                0.28,
                0.22,
                label,
                ha="left",
                va="center",
                fontsize=t.kpi_label_size,
                color=t.muted,
                zorder=3,
            )

    def _draw_main_chart_card(self, fig, subplot_spec, metrics: TeamMonthMetrics) -> None:
        t = self.theme
        outer = fig.add_subplot(subplot_spec)
        self._card(outer)

        y_leg = 0.92
        outer.text(
            0.04,
            y_leg,
            "Время по дням",
            ha="left",
            va="center",
            fontsize=t.section_size,
            color=t.ink,
            fontweight="semibold",
            zorder=3,
        )

        # Participants after title
        x = 0.26
        for u in metrics.users:
            outer.plot([x], [y_leg], marker="o", markersize=6, color=u.color, zorder=3)
            outer.text(
                x + 0.014,
                y_leg,
                u.name,
                ha="left",
                va="center",
                fontsize=t.small_size,
                color=t.ink,
                zorder=3,
            )
            x += 0.12 + min(len(u.name), 12) * 0.0055

        # Work / rest — fixed on the right of the same line
        for box_x, label, filled in (
            (0.72, "время работы", True),
            (0.86, "отдых", False),
        ):
            outer.add_patch(
                FancyBboxPatch(
                    (box_x - 0.008, y_leg - 0.022),
                    0.015,
                    0.044,
                    boxstyle="round,pad=0.001,rounding_size=0.004",
                    linewidth=1.4 if not filled else 0,
                    edgecolor=t.muted if not filled else "none",
                    facecolor=t.ink if filled else "none",
                    zorder=3,
                    transform=outer.transData,
                    clip_on=False,
                )
            )
            outer.text(
                box_x + 0.016,
                y_leg,
                label,
                ha="left",
                va="center",
                fontsize=t.small_size,
                color=t.muted,
                zorder=3,
            )

        chart_ax = outer.inset_axes([0.06, 0.10, 0.90, 0.74])
        self.chart.draw(chart_ax, metrics)

    def _draw_sidebar(self, fig, subplot_spec, metrics: TeamMonthMetrics) -> None:
        t = self.theme
        ax = fig.add_subplot(subplot_spec)
        self._card(ax)

        if t.stacked_mid:
            self._draw_sidebar_horizontal(ax, metrics)
        else:
            self._draw_sidebar_vertical(ax, metrics)

    def _draw_sidebar_vertical(self, ax, metrics: TeamMonthMetrics) -> None:
        t = self.theme
        ax.text(
            0.5,
            0.92,
            "Итоги месяца",
            ha="center",
            va="center",
            fontsize=t.section_size,
            color=t.ink,
            fontweight="semibold",
            zorder=3,
        )
        donut_ax = ax.inset_axes([0.12, 0.12, 0.76, 0.70])
        self._draw_donut(donut_ax, metrics)

    def _draw_sidebar_horizontal(self, ax, metrics: TeamMonthMetrics) -> None:
        t = self.theme
        ax.text(
            0.04,
            0.82,
            "Итоги месяца",
            ha="left",
            va="center",
            fontsize=t.section_size,
            color=t.ink,
            fontweight="semibold",
            zorder=3,
        )
        donut_ax = ax.inset_axes([0.30, 0.10, 0.40, 0.72])
        self._draw_donut(donut_ax, metrics)

    def _draw_activity_bars(
        self,
        ax,
        metrics: TeamMonthMetrics,
        *,
        x0: float,
        y0: float,
        width: float,
        height: float,
    ) -> None:
        act = metrics.daily_team_totals
        if not act:
            return
        window = act[-14:] if len(act) > 14 else act
        peak = max(window) or 1.0
        n = len(window)
        for i, val in enumerate(window):
            bx = x0 + i * (width / max(n, 1))
            bw = width / max(n, 1) * 0.55
            bh = height * (val / peak)
            ax.add_patch(
                FancyBboxPatch(
                    (bx, y0),
                    bw,
                    max(bh, 0.008),
                    boxstyle="round,pad=0.001,rounding_size=0.01",
                    linewidth=0,
                    facecolor="#C7C7CC",
                    zorder=3,
                )
            )

    def _draw_donut(self, ax, metrics: TeamMonthMetrics) -> None:
        t = self.theme
        ax.set_xlim(-1.2, 1.2)
        ax.set_ylim(-1.2, 1.2)
        ax.set_aspect("equal")
        ax.axis("off")

        shares = metrics.shares
        if not metrics.users or metrics.team_total <= 0:
            ax.add_patch(
                Circle((0, 0), 1.0, facecolor=t.border, edgecolor="none")
            )
        else:
            start = 90.0
            for u, share in zip(metrics.users, shares):
                theta = share * 360.0
                if theta <= 0:
                    continue
                wedge = Wedge(
                    (0, 0),
                    1.0,
                    start,
                    start + theta,
                    width=0.38,
                    facecolor=u.color,
                    edgecolor=t.card_bg,
                    linewidth=1.5,
                )
                ax.add_patch(wedge)
                mid = start + theta / 2
                # percent label outside ring for larger slices
                if share >= 0.08:
                    rad = math.radians(mid)
                    ax.text(
                        0.72 * math.cos(rad),
                        0.72 * math.sin(rad),
                        f"{int(round(share * 100))}%",
                        ha="center",
                        va="center",
                        fontsize=7,
                        color=t.ink,
                        fontweight="bold",
                    )
                start += theta

        ax.add_patch(Circle((0, 0), 0.55, facecolor=t.card_bg, edgecolor="none"))
        total = format_duration(metrics.team_total) if metrics.team_total else "0ч"
        # Split for two-line center if possible
        parts = total.replace(" ", "\n", 1) if " " in total else total
        ax.text(
            0,
            0,
            parts,
            ha="center",
            va="center",
            fontsize=9,
            color=t.ink,
            fontweight="bold",
            linespacing=1.15,
        )

    def _draw_user_card(
        self,
        fig,
        subplot_spec,
        user: UserMonthMetrics,
        last_day: int,
    ) -> None:
        t = self.theme
        ax = fig.add_subplot(subplot_spec)
        self._card(ax)
        self._avatar(ax, 0.12, 0.78, user, r=0.07)
        ax.text(
            0.24,
            0.78,
            user.name,
            ha="left",
            va="center",
            fontsize=t.body_size,
            color=t.ink,
            fontweight="semibold",
            zorder=3,
        )
        ax.text(
            0.08,
            0.58,
            MetricsCalculator.fmt(user.total_hours),
            ha="left",
            va="center",
            fontsize=t.kpi_value_size + 2,
            color=t.ink,
            fontweight="bold",
            zorder=3,
        )

        # Sparkline
        spark = ax.inset_axes([0.08, 0.34, 0.84, 0.16])
        spark.axis("off")
        xs = list(range(last_day))
        ys = user.daily_hours
        spark.plot(xs, ys, color=user.color, linewidth=1.4, solid_capstyle="round")
        spark.fill_between(xs, ys, color=user.color, alpha=0.12)
        spark.set_xlim(0, max(last_day - 1, 1))
        spark.set_ylim(0, max(max(ys) * 1.2, 0.1) if ys else 1)

        stats = [
            ("среднее", MetricsCalculator.fmt(user.avg_active_hours)),
            ("макс.", MetricsCalculator.fmt(user.max_day_hours)),
        ]
        for i, (lab, val) in enumerate(stats):
            x = 0.08 + i * 0.46
            ax.text(
                x,
                0.22,
                val,
                ha="left",
                va="center",
                fontsize=t.small_size + 0.5,
                color=t.ink,
                fontweight="semibold",
                zorder=3,
            )
            ax.text(
                x,
                0.10,
                lab,
                ha="left",
                va="center",
                fontsize=t.small_size - 0.5,
                color=t.muted,
                zorder=3,
            )

    def _draw_leader_card(self, fig, subplot_spec, metrics: TeamMonthMetrics) -> None:
        t = self.theme
        ax = fig.add_subplot(subplot_spec)
        self._card(ax, accent="#F3E8FF")
        leader = metrics.leader

        if t.leader_own_row:
            self._draw_leader_banner(ax, leader)
        else:
            self._draw_leader_compact(ax, leader)

    def _draw_leader_banner(self, ax, leader: UserMonthMetrics | None) -> None:
        """Full-width strip: three equal columns, each block centered."""
        t = self.theme
        c1, c2, c3 = 1 / 6, 0.5, 5 / 6

        for x in (1 / 3, 2 / 3):
            ax.plot(
                [x, x],
                [0.22, 0.78],
                color="#E0D4F5",
                linewidth=1.0,
                solid_capstyle="round",
                zorder=2,
                clip_on=False,
            )

        # Column 1 — star over title
        self._round_icon(ax, c1, 0.62, color=t.leader_accent, glyph="★", size=24)
        ax.text(
            c1,
            0.36,
            "Лидер месяца",
            ha="center",
            va="center",
            fontsize=t.section_size,
            color=t.leader_accent,
            fontweight="semibold",
            zorder=3,
        )

        # Column 2 — name + caption
        if leader and leader.total_hours > 0:
            ax.text(
                c2,
                0.58,
                leader.name,
                ha="center",
                va="center",
                fontsize=t.kpi_value_size,
                color=t.ink,
                fontweight="bold",
                zorder=3,
            )
            ax.text(
                c2,
                0.36,
                "больше всех часов",
                ha="center",
                va="center",
                fontsize=t.small_size + 0.5,
                color=t.muted,
                zorder=3,
            )
            # Column 3 — hours (vertically centered in column)
            ax.text(
                c3,
                0.50,
                MetricsCalculator.fmt(leader.total_hours),
                ha="center",
                va="center",
                fontsize=t.kpi_value_size + 4,
                color=t.leader_accent,
                fontweight="bold",
                zorder=3,
            )
        else:
            ax.text(
                c2,
                0.50,
                "Пока нет данных",
                ha="center",
                va="center",
                fontsize=t.body_size,
                color=t.muted,
                zorder=3,
            )

    def _draw_leader_compact(self, ax, leader: UserMonthMetrics | None) -> None:
        """Square-ish side card: vertical stack with even gaps."""
        t = self.theme
        ax.text(
            0.5,
            0.88,
            "Лидер месяца",
            ha="center",
            va="center",
            fontsize=t.section_size,
            color=t.leader_accent,
            fontweight="semibold",
            zorder=3,
        )
        self._round_icon(ax, 0.5, 0.64, color=t.leader_accent, glyph="★", size=30)
        if leader and leader.total_hours > 0:
            ax.text(
                0.5,
                0.42,
                leader.name,
                ha="center",
                va="center",
                fontsize=t.body_size + 1,
                color=t.ink,
                fontweight="bold",
                zorder=3,
            )
            ax.text(
                0.5,
                0.26,
                MetricsCalculator.fmt(leader.total_hours),
                ha="center",
                va="center",
                fontsize=t.kpi_value_size + 2,
                color=t.leader_accent,
                fontweight="bold",
                zorder=3,
            )
            ax.text(
                0.5,
                0.12,
                "больше всех часов",
                ha="center",
                va="center",
                fontsize=t.small_size,
                color=t.muted,
                zorder=3,
            )
        else:
            ax.text(
                0.5,
                0.35,
                "Пока нет данных",
                ha="center",
                va="center",
                fontsize=t.body_size,
                color=t.muted,
                zorder=3,
            )
