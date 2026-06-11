"""Run DE+FR sensitivity checks for alternative ranking criteria."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from heatwave_definition.legacy import LegacyMetricsData, load_legacy_metrics_pickle
from heatwave_definition.ranking import rank_years_by_grid_metric


REPO = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = REPO / "outputs" / "sensitivity"
DEFAULT_FIGURE_DIR = REPO / "outputs" / "figures"

DATASETS = [
    ("Historical / E-OBS", "metrics_e_obs.pkl"),
    ("RCP4.5 / IPSL-WRF", "metrics_copernicus_45.pkl"),
    ("RCP8.5 / MPI-CLM", "metrics_copernicus_85.pkl"),
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
        "Area-weighted annual Tmax anomaly",
        "temp_anomaly",
        "area_weighted_mean",
    ),
]


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    args.figure_dir.mkdir(parents=True, exist_ok=True)

    rows = []
    for dataset, filename in DATASETS:
        data = load_legacy_metrics_pickle(args.repo / filename)
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


def metric_array(data: LegacyMetricsData, metric_name: str) -> np.ndarray | None:
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
    values = rank1.loc[criteria_order, dataset_order].astype(float)
    labels = labels.loc[criteria_order, dataset_order]

    fig_height = max(3.6, 0.52 * len(values.index) + 1.4)
    fig, ax = plt.subplots(figsize=(8.4, fig_height), constrained_layout=True)
    image = ax.imshow(values.to_numpy(), cmap="viridis", aspect="auto")
    ax.set_xticks(np.arange(len(values.columns)), values.columns, rotation=20, ha="right")
    ax.set_yticks(np.arange(len(values.index)), values.index)
    ax.set_title("Top-ranked years by ranking criterion (rank 2 in parentheses)")
    ax.tick_params(length=0)

    for row in range(values.shape[0]):
        for col in range(values.shape[1]):
            ax.text(col, row, labels.iloc[row, col], ha="center", va="center", color="white", fontsize=8)

    cbar = fig.colorbar(image, ax=ax, shrink=0.82)
    cbar.set_label("Rank-1 year")
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, dpi=220)
    plt.close(fig)


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
