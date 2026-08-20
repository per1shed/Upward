"""Apple-style dashboard theme: colors, sizes, fonts, spacing."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Theme:
    # Canvas — вариант E: широкий график + лидер отдельной строкой
    width_px: int = 1800
    height_px: int = 1280
    dpi: int = 140
    bg: str = "#F8F8FA"
    card_bg: str = "#FFFFFF"
    border: str = "#ECECEC"
    ink: str = "#111111"
    muted: str = "#7A7A7A"
    grid: str = "#EFEFEF"
    weekend: str = "#FF3B30"
    weekend_band: str = "#F0F0F2"
    leader_accent: str = "#BF5AF2"

    # Participant palette (Apple HIG system colors)
    user_colors: tuple[str, ...] = (
        "#0A84FF",
        "#FF9F0A",
        "#30D158",
        "#5E5CE6",
        "#FF375F",
        "#64D2FF",
    )

    # Geometry
    card_radius_pt: float = 18.0
    chip_radius_pt: float = 14.0
    rest_linewidth: float = 2.0
    shadow_alpha: float = 0.07

    # Typography (pt)
    font_family: str = "DejaVu Sans"
    title_size: float = 22.0
    subtitle_size: float = 11.0
    kpi_value_size: float = 16.0
    kpi_label_size: float = 9.0
    section_size: float = 12.0
    axis_size: float = 9.0
    bar_label_size: float = 8.5
    body_size: float = 10.0
    small_size: float = 8.0

    # Layout (вариант E)
    margin_x: float = 0.025
    margin_y: float = 0.018
    gap: float = 0.012
    # chart+donut | user cards | leader  (KPI added separately when enabled)
    height_ratios: tuple[float, float, float] = (3.4, 1.7, 0.85)
    show_header: bool = False
    show_kpi_row: bool = True
    mid_width_ratios: tuple[float, float] = (2.8, 1.0)
    stacked_mid: bool = False
    leader_own_row: bool = True
    hspace: float = 0.10
    layout_label: str = ""

    # Chart
    group_width: float = 0.78
    y_pad_hours: float = 1.0
    y_min_top: float = 2.0

    kpi_icon_colors: tuple[str, ...] = field(
        default_factory=lambda: (
            "#0A84FF",
            "#FFD60A",
            "#BF5AF2",
        )
    )


MONTH_GENITIVE = (
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

WEEKDAY_SHORT = ("пн", "вт", "ср", "чт", "пт", "сб", "вс")
