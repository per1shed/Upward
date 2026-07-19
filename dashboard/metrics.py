"""Compute dashboard metrics from monthly DayEntry series."""
from __future__ import annotations

import calendar
import datetime as dt
from dataclasses import dataclass, field

from database import DayEntry
from time_format import format_duration

from dashboard.theme import MONTH_GENITIVE


@dataclass
class UserMonthMetrics:
    name: str
    color: str
    letter: str
    daily_hours: list[float]
    daily_rest: list[bool]
    daily_breakthrough: list[bool]
    total_hours: float = 0.0
    active_days: int = 0
    marked_days: int = 0
    max_day_hours: float = 0.0
    avg_active_hours: float = 0.0


@dataclass
class TeamMonthMetrics:
    year: int
    month: int
    last_day: int
    users: list[UserMonthMetrics] = field(default_factory=list)
    team_total: float = 0.0
    best_day: dt.date | None = None
    best_day_hours: float = 0.0
    daily_max: float = 0.0
    avg_day_hours: float = 0.0
    active_days_team: int = 0
    daily_team_totals: list[float] = field(default_factory=list)

    @property
    def shares(self) -> list[float]:
        if self.team_total <= 0:
            n = len(self.users) or 1
            return [1.0 / n] * len(self.users)
        return [u.total_hours / self.team_total for u in self.users]

    @property
    def leader(self) -> UserMonthMetrics | None:
        if not self.users:
            return None
        return max(self.users, key=lambda u: u.total_hours)

    def format_best_day(self) -> str:
        if self.best_day is None:
            return "—"
        return f"{self.best_day.day} {MONTH_GENITIVE[self.best_day.month]}"


class MetricsCalculator:
    @staticmethod
    def _letter(name: str) -> str:
        cleaned = name.lstrip("@").strip()
        return (cleaned[:1] or "?").upper()

    @classmethod
    def compute(
        cls,
        users_series: list[tuple[str, str, dict[dt.date, DayEntry]]],
        year: int,
        month: int,
    ) -> TeamMonthMetrics:
        """users_series: (display_name, color, entries)."""
        _, last_day = calendar.monthrange(year, month)
        all_days = [dt.date(year, month, d) for d in range(1, last_day + 1)]
        metrics = TeamMonthMetrics(year=year, month=month, last_day=last_day)

        for name, color, entries in users_series:
            daily_h = [0.0] * last_day
            daily_rest = [False] * last_day
            daily_br = [False] * last_day
            for day in all_days:
                entry = entries.get(day)
                if entry is None:
                    continue
                i = day.day - 1
                daily_rest[i] = entry.is_rest
                daily_br[i] = entry.is_breakthrough
                if entry.is_rest:
                    continue
                if entry.hours > 0:
                    daily_h[i] = entry.hours

            total = sum(daily_h)
            active = sum(1 for h in daily_h if h > 0)
            marked = 0
            for day in all_days:
                e = entries.get(day)
                if e and (e.is_rest or e.is_breakthrough or e.hours > 0):
                    marked += 1
            max_h = max(daily_h) if daily_h else 0.0
            avg = total / active if active else 0.0
            metrics.users.append(
                UserMonthMetrics(
                    name=name,
                    color=color,
                    letter=cls._letter(name),
                    daily_hours=daily_h,
                    daily_rest=daily_rest,
                    daily_breakthrough=daily_br,
                    total_hours=total,
                    active_days=active,
                    marked_days=marked,
                    max_day_hours=max_h,
                    avg_active_hours=avg,
                )
            )

        metrics.team_total = sum(u.total_hours for u in metrics.users)
        metrics.daily_team_totals = [
            sum(u.daily_hours[d] for u in metrics.users) for d in range(last_day)
        ]

        best_person_day = 0.0
        best_date: dt.date | None = None
        for day in all_days:
            for u in metrics.users:
                h = u.daily_hours[day.day - 1]
                if h > best_person_day:
                    best_person_day = h
                    best_date = day

        metrics.best_day = best_date
        metrics.best_day_hours = best_person_day
        metrics.daily_max = best_person_day

        work_days = [t for t in metrics.daily_team_totals if t > 0]
        metrics.active_days_team = len(work_days)
        metrics.avg_day_hours = (
            sum(work_days) / len(work_days) if work_days else 0.0
        )
        return metrics

    @staticmethod
    def fmt(hours: float) -> str:
        return format_duration(hours) if hours > 0 else "0ч"
