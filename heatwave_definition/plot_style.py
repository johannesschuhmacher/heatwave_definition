"""Shared plot styling for manuscript figures."""

from __future__ import annotations

from dataclasses import dataclass

from matplotlib.colors import BoundaryNorm, ListedColormap
from matplotlib.patches import Patch
import matplotlib.pyplot as plt


DATASET_ORDER = ["Historical / E-OBS", "RCP4.5 / IPSL-WRF", "RCP8.5 / MPI-CLM"]
DATASET_DISPLAY = {
    "Historical / E-OBS": "Historical\nE-OBS",
    "RCP4.5 / IPSL-WRF": "RCP4.5\nIPSL-WRF",
    "RCP8.5 / MPI-CLM": "RCP8.5\nMPI-CLM",
}

DATASET_COLORS = {
    "Historical / E-OBS": "#000000",
    "RCP4.5 / IPSL-WRF": "#0072B2",
    "RCP8.5 / MPI-CLM": "#D55E00",
}
DATASET_LINESTYLES = {
    "Historical / E-OBS": "-",
    "RCP4.5 / IPSL-WRF": "--",
    "RCP8.5 / MPI-CLM": "-.",
}
DATASET_MARKERS = {
    "Historical / E-OBS": "o",
    "RCP4.5 / IPSL-WRF": "s",
    "RCP8.5 / MPI-CLM": "^",
}


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


def apply_manuscript_style() -> None:
    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "axes.titlesize": 14,
            "axes.labelsize": 10,
            "xtick.labelsize": 9,
            "ytick.labelsize": 9,
            "legend.fontsize": 8.5,
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

