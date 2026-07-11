"""Shared plot styling for manuscript figures."""

from __future__ import annotations

from dataclasses import dataclass

from matplotlib.colors import BoundaryNorm, ListedColormap
from matplotlib.patches import Patch
import matplotlib.pyplot as plt


DATASET_ORDER = ["Historical / E-OBS", "Historical / ERA5", "RCP4.5 / IPSL-WRF", "RCP8.5 / MPI-CLM"]
DATASET_DISPLAY = {
    "Historical / E-OBS": "Historical\nE-OBS",
    "Historical / ERA5": "Historical\nERA5",
    "RCP4.5 / IPSL-WRF": "RCP4.5\nIPSL-WRF",
    "RCP8.5 / MPI-CLM": "RCP8.5\nMPI-CLM",
}

DATASET_COLORS = {
    "Historical / E-OBS": "#000000",
    "Historical / ERA5": "#009E73",
    "RCP4.5 / IPSL-WRF": "#0072B2",
    "RCP8.5 / MPI-CLM": "#D55E00",
}
DATASET_LINESTYLES = {
    "Historical / E-OBS": "-",
    "Historical / ERA5": (0, (3, 1.5)),
    "RCP4.5 / IPSL-WRF": "--",
    "RCP8.5 / MPI-CLM": "-.",
}
DATASET_MARKERS = {
    "Historical / E-OBS": "o",
    "Historical / ERA5": "D",
    "RCP4.5 / IPSL-WRF": "s",
    "RCP8.5 / MPI-CLM": "^",
}

TITLE_SIZE = 14
SUBTITLE_SIZE = 9.5
PANEL_TITLE_SIZE = 10.5
AXIS_LABEL_SIZE = 10
TICK_LABEL_SIZE = 8.8
LEGEND_SIZE = 8.3
ANNOTATION_SIZE = 7.8
SMALL_TEXT_SIZE = 7.3
TEXT_COLOR = "#172033"
SECONDARY_TEXT_COLOR = "#555555"


@dataclass(frozen=True)
class StabilityCategory:
    key: str
    code: int
    label: str
    color: str
    text_color: str


STABILITY_CATEGORIES = [
    StabilityCategory(
        "match_both",
        0,
        "rank 1 and rank 2 match reference",
        "#6F812C",
        "white",
    ),
    StabilityCategory(
        "rank1_match",
        1,
        "rank 1 matches; rank 2 changes",
        "#AEB979",
        "#172033",
    ),
    StabilityCategory(
        "rank1_changes_reference_retained",
        2,
        "rank 1 changes; reference year retained",
        "#D9D2A5",
        "#172033",
    ),
    StabilityCategory(
        "no_reference_top2",
        3,
        "no reference year in top 2",
        "#D6D8E4",
        "#172033",
    ),
]

STABILITY_BY_KEY = {category.key: category for category in STABILITY_CATEGORIES}
STABILITY_BY_CODE = {category.code: category for category in STABILITY_CATEGORIES}
STABILITY_CMAP = ListedColormap([category.color for category in STABILITY_CATEGORIES])
STABILITY_NORM = BoundaryNorm(
    [category.code - 0.5 for category in STABILITY_CATEGORIES] + [STABILITY_CATEGORIES[-1].code + 0.5],
    STABILITY_CMAP.N,
)

HWMID_BINS = [0, 3, 6, 9, 15, 24, 36, 48, 96]
HWMID_COLORS = ["#F7F7F7", "#D9D9D9", "#BDBDBD", "#FEE391", "#FDB863", "#E66101", "#B2182B", "#67001F"]
HWMID_CMAP = ListedColormap(HWMID_COLORS)
HWMID_NORM = BoundaryNorm(HWMID_BINS, HWMID_CMAP.N)


def apply_manuscript_style() -> None:
    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.sans-serif": ["DejaVu Sans"],
            "axes.titlesize": PANEL_TITLE_SIZE,
            "axes.labelsize": AXIS_LABEL_SIZE,
            "xtick.labelsize": TICK_LABEL_SIZE,
            "ytick.labelsize": TICK_LABEL_SIZE,
            "legend.fontsize": LEGEND_SIZE,
            "figure.titlesize": TITLE_SIZE,
            "figure.dpi": 120,
            "savefig.dpi": 220,
            "savefig.bbox": "tight",
        }
    )


def classify_top2_stability(reference_top2: tuple[int, int], candidate_top2: tuple[int, int]) -> StabilityCategory:
    reference_rank1, reference_rank2 = reference_top2
    candidate_rank1, candidate_rank2 = candidate_top2
    reference_set = {reference_rank1, reference_rank2}
    candidate_set = {candidate_rank1, candidate_rank2}

    if candidate_rank1 == reference_rank1 and candidate_rank2 == reference_rank2:
        return STABILITY_BY_KEY["match_both"]
    if candidate_rank1 == reference_rank1:
        return STABILITY_BY_KEY["rank1_match"]
    if reference_set.intersection(candidate_set):
        return STABILITY_BY_KEY["rank1_changes_reference_retained"]
    return STABILITY_BY_KEY["no_reference_top2"]


def stability_legend_handles() -> list[Patch]:
    return [
        Patch(
            facecolor=category.color,
            edgecolor="#3A3A3A",
            label=category.label,
        )
        for category in STABILITY_CATEGORIES
    ]

