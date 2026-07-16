"""Run Germany-France sensitivity checks for alternative ranking criteria."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import textwrap

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from heatwave_definition.metrics import MetricsData, load_metrics_file, resolve_metrics_file
from heatwave_definition.plot_style import (
    ANNOTATION_SIZE,
    DATASET_DISPLAY,
    LEGEND_SIZE,
    PANEL_TITLE_SIZE,
    STABILITY_CMAP,
    STABILITY_NORM,
    apply_manuscript_style,
    classify_top2_stability,
    stability_legend_handles,
)
from heatwave_definition.ranking import rank_years_by_grid_metric


REPO = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = REPO / "outputs" / "sensitivity"
DEFAULT_FIGURE_DIR = REPO / "outputs" / "figures"

DATASETS = [
    ("Historical / E-OBS", ["metrics_e_obs.npz"]),
    ("RCP4.5 / IPSL-WRF", ["metrics_copernicus_rcp45.npz"]),
    ("RCP8.5 / MPI-CLM", ["metrics_copernicus_rcp85.npz"]),
]


@dataclass(frozen=True)
class Criterion:
    key: str
    label: str
    metric_name: str
    aggregation: str


CRITERIA = [
    Criterion("hwmid_sum", "HWMId sum", "hwmid", "sum"),
    Criterion("hwmid_area_mean", "Area-weighted HWMId mean", "hwmid", "area_weighted_mean"),
    Criterion("hwmid_mean", "Mean HWMId", "hwmid", "mean"),
    Criterion("hwmid_max", "Maximum grid-cell HWMId", "hwmid", "max"),
    Criterion(
        "duration_area_mean",
        "Area-weighted heatwave duration",
        "heatwave_duration",
        "area_weighted_mean",
    ),
    Criterion(
        "tmax_anomaly_area_mean",
        "Area-weighted annual maximum temperature anomaly",
        "temp_anomaly",
        "area_weighted_mean",
    ),
]


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    apply_manuscript_style()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    args.figure_dir.mkdir(parents=True, exist_ok=True)

    rows = []
    for dataset, filenames in DATASETS:
        data = load_metrics_file(resolve_metrics_file(args.repo, filenames))
        for criterion in CRITERIA:
            metric = metric_array(data, criterion.metric_name)
            if metric is None:
                continue
            ranking = rank_years_by_grid_metric(
                data.latitude,
                data.longitude,
                metric,
                data.dates,
                no_years=args.top_years,
                countries=args.countries,
                aggregation=criterion.aggregation,
                score_column="score",
            )
            ranking.insert(0, "dataset", dataset)
            ranking.insert(1, "criterion", criterion.key)
            ranking.insert(2, "criterion_label", criterion.label)
            ranking.insert(3, "metric", criterion.metric_name)
            ranking["hwmid_method"] = data.hwmid_method
            rows.append(ranking)

    if not rows:
        raise SystemExit("No ranking criteria could be evaluated.")

    result = pd.concat(rows, ignore_index=True)
    full_path = args.output_dir / "ranking_criteria_top_years.csv"
    result.to_csv(full_path, index=False)

    top2 = result[result["rank"] <= 2].copy()
    summary_path = args.output_dir / "ranking_criteria_top2_summary.csv"
    top2.to_csv(summary_path, index=False)

    heatmap_path = args.figure_dir / "ranking_criteria_top2_heatmap_de_fr.png"
    plot_heatmap(top2, heatmap_path)

    print(full_path)
    print(summary_path)
    print(heatmap_path)


def metric_array(data: MetricsData, metric_name: str) -> np.ndarray | None:
    return getattr(data, metric_name)


def plot_heatmap(top2: pd.DataFrame, output: Path) -> None:
    rank1 = top2[top2["rank"] == 1].pivot(index="criterion_label", columns="dataset", values="year")
    labels = rank1.copy().astype(str)
    rank2 = top2[top2["rank"] == 2].pivot(index="criterion_label", columns="dataset", values="year")
    for row in labels.index:
        for col in labels.columns:
            labels.loc[row, col] = f"{int(rank1.loc[row, col])}\n({int(rank2.loc[row, col])})"

    criteria_order = [criterion.label for criterion in CRITERIA if criterion.label in rank1.index]
    dataset_order = [dataset for dataset, _ in DATASETS if dataset in rank1.columns]
    labels = labels.loc[criteria_order, dataset_order]
    codes = np.zeros((len(criteria_order), len(dataset_order)), dtype=int)
    text_colors = [["" for _ in dataset_order] for _ in criteria_order]

    for col_idx, dataset in enumerate(dataset_order):
        reference_top2 = (
            int(rank1.loc["HWMId sum", dataset]),
            int(rank2.loc["HWMId sum", dataset]),
        )
        for row_idx, criterion in enumerate(criteria_order):
            candidate_top2 = (
                int(rank1.loc[criterion, dataset]),
                int(rank2.loc[criterion, dataset]),
            )
            category = classify_top2_stability(reference_top2, candidate_top2)
            codes[row_idx, col_idx] = category.code
            text_colors[row_idx][col_idx] = category.text_color

    fig_height = max(3.6, 0.52 * len(criteria_order) + 1.4)
    fig, ax = plt.subplots(figsize=(7.2, fig_height + 0.4), constrained_layout=True)
    ax.imshow(codes, cmap=STABILITY_CMAP, norm=STABILITY_NORM, aspect="auto")
    ax.set_xticks(
        np.arange(len(dataset_order)),
        [DATASET_DISPLAY.get(dataset, dataset) for dataset in dataset_order],
    )
    ax.set_yticks(np.arange(len(criteria_order)), [wrap_label(label, 22) for label in criteria_order])
    ax.set_title("Top-ranked years by ranking criterion (rank 2 in parentheses)", fontsize=PANEL_TITLE_SIZE)
    ax.tick_params(length=0)

    for row in range(codes.shape[0]):
        for col in range(codes.shape[1]):
            ax.text(
                col,
                row,
                labels.iloc[row, col],
                ha="center",
                va="center",
                color=text_colors[row][col],
                fontsize=ANNOTATION_SIZE,
                fontweight="bold",
            )

    ax.legend(
        handles=stability_legend_handles(),
        frameon=False,
        ncol=2,
        loc="upper center",
        bbox_to_anchor=(0.5, -0.16),
        fontsize=LEGEND_SIZE,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, dpi=220)
    plt.close(fig)


def heatmap_text_color(value: float, image) -> str:
    red, green, blue, _ = image.cmap(image.norm(value))
    luminance = 0.2126 * red + 0.7152 * green + 0.0722 * blue
    return "black" if luminance > 0.55 else "white"


def wrap_label(label: str, width: int) -> str:
    return "\n".join(textwrap.wrap(label, width=width))


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=REPO)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--figure-dir", type=Path, default=DEFAULT_FIGURE_DIR)
    parser.add_argument("--countries", nargs="+", default=["Germany", "France"])
    parser.add_argument("--top-years", type=int, default=10)
    return parser.parse_args(argv)


if __name__ == "__main__":
    main()
