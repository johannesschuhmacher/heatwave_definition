"""Compare historical E-OBS and ERA5 heatwave-year rankings."""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

from heatwave_definition.plot_style import (
    ANNOTATION_SIZE,
    AXIS_LABEL_SIZE,
    DATASET_COLORS,
    DATASET_LINESTYLES,
    DATASET_MARKERS,
    LEGEND_SIZE,
    PANEL_TITLE_SIZE,
    SUBTITLE_SIZE,
    TITLE_SIZE,
    apply_manuscript_style,
)


REPO = Path(__file__).resolve().parents[1]
DEFAULT_EOBS = REPO / "outputs" / "eobs_current" / "ranked_years_eobs_v33_historical.csv"
DEFAULT_ERA5 = REPO / "outputs" / "ranking_from_config" / "ranked_years_era5.csv"
DEFAULT_OUTPUT_DIR = REPO / "outputs" / "appendix"
DEFAULT_FIGURE = REPO / "outputs" / "figures" / "historical_data_product_top10_comparison.png"


def main() -> None:
    args = parse_args()
    apply_manuscript_style()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    args.figure.parent.mkdir(parents=True, exist_ok=True)

    top10 = build_common_period_top10(args.eobs, args.era5, args.start_year, args.end_year)
    top10_path = args.output_dir / "historical_data_product_top10_common_period.csv"
    top10.to_csv(top10_path, index=False)

    top2 = build_top2_comparison(top10)
    top2_path = args.output_dir / "historical_data_product_top2_comparison.csv"
    top2.to_csv(top2_path, index=False)

    plot_comparison(top10, args.figure, args.start_year, args.end_year)

    print(top10_path)
    print(top2_path)
    print(args.figure)
    print(top2.to_string(index=False))


def build_common_period_top10(eobs_path: Path, era5_path: Path, start_year: int, end_year: int) -> pd.DataFrame:
    frames = []
    for dataset, path, product, period in [
        ("Historical / E-OBS", eobs_path, "E-OBS v33.0e", f"{start_year}-{end_year} common period"),
        ("Historical / ERA5", era5_path, "ERA5", f"{start_year}-{end_year} common period"),
    ]:
        table = pd.read_csv(path)
        subset = table[(table["year"] >= start_year) & (table["year"] <= end_year)].copy()
        subset = subset.sort_values("hwmid_sum", ascending=False).head(10).reset_index(drop=True)
        subset["rank"] = range(1, len(subset) + 1)
        subset.insert(0, "dataset", dataset)
        subset.insert(1, "data_product", product)
        subset.insert(2, "comparison_period", period)
        frames.append(subset[["dataset", "data_product", "comparison_period", "rank", "year", "hwmid_sum", "country_cells"]])
    return pd.concat(frames, ignore_index=True)


def build_top2_comparison(top10: pd.DataFrame) -> pd.DataFrame:
    rows = []
    eobs = top10[top10["dataset"] == "Historical / E-OBS"].set_index("rank")
    era5 = top10[top10["dataset"] == "Historical / ERA5"].set_index("rank")
    for rank in [1, 2]:
        eobs_value = float(eobs.loc[rank, "hwmid_sum"])
        era5_value = float(era5.loc[rank, "hwmid_sum"])
        rows.append(
            {
                "rank": rank,
                "eobs_year": int(eobs.loc[rank, "year"]),
                "eobs_hwmid_sum": eobs_value,
                "era5_year": int(era5.loc[rank, "year"]),
                "era5_hwmid_sum": era5_value,
                "same_year": int(eobs.loc[rank, "year"]) == int(era5.loc[rank, "year"]),
                "era5_minus_eobs_hwmid_sum": era5_value - eobs_value,
                "era5_minus_eobs_percent": ((era5_value - eobs_value) / eobs_value) * 100.0,
            }
        )
    return pd.DataFrame(rows)


def plot_comparison(top10: pd.DataFrame, output: Path, start_year: int, end_year: int) -> None:
    fig, ax = plt.subplots(figsize=(8.2, 4.8))
    fig.subplots_adjust(left=0.09, right=0.98, bottom=0.14, top=0.74)
    offsets = {
        "Historical / E-OBS": (0, 8),
        "Historical / ERA5": (0, -14),
    }
    for dataset in ["Historical / E-OBS", "Historical / ERA5"]:
        group = top10[top10["dataset"] == dataset].sort_values("rank")
        color = DATASET_COLORS[dataset]
        ax.plot(
            group["rank"],
            group["hwmid_sum"],
            marker=DATASET_MARKERS[dataset],
            linestyle=DATASET_LINESTYLES[dataset],
            linewidth=2.2,
            markersize=5.5,
            color=color,
            label=dataset.replace("Historical / ", ""),
        )
        for _, row in group.iterrows():
            ax.annotate(
                str(int(row["year"])),
                (row["rank"], row["hwmid_sum"]),
                textcoords="offset points",
                xytext=offsets[dataset],
                ha="center",
                fontsize=ANNOTATION_SIZE,
                color=color,
            )
    fig.suptitle("Historical heatwave-year ranking by data product", fontsize=TITLE_SIZE, y=0.99)
    fig.text(
        0.5,
        0.925,
        f"E-OBS and ERA5 select the same leading benchmark years in the common period {start_year}-{end_year}.",
        ha="center",
        fontsize=SUBTITLE_SIZE,
        color="#555555",
    )
    fig.text(
        0.5,
        0.895,
        "Germany-France mask; HWMId reference period 1981-2010.",
        ha="center",
        fontsize=SUBTITLE_SIZE,
        color="#555555",
    )
    ax.set_xlabel("Rank", fontsize=AXIS_LABEL_SIZE)
    ax.set_ylabel("HWMId sum over Germany and France", fontsize=AXIS_LABEL_SIZE)
    ax.set_xticks(range(1, 11))
    ax.set_ylim(3000, 27500)
    ax.grid(axis="y", alpha=0.25)
    ax.spines[["top", "right"]].set_visible(False)
    ax.legend(frameon=False, loc="upper right", fontsize=LEGEND_SIZE)
    fig.savefig(output, dpi=220, bbox_inches="tight")
    plt.close(fig)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--eobs", type=Path, default=DEFAULT_EOBS)
    parser.add_argument("--era5", type=Path, default=DEFAULT_ERA5)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--figure", type=Path, default=DEFAULT_FIGURE)
    parser.add_argument("--start-year", type=int, default=1950)
    parser.add_argument("--end-year", type=int, default=2025)
    return parser.parse_args()


if __name__ == "__main__":
    main()
