"""Compare historical HWMId rankings at alternative threshold quantiles."""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

from heatwave_definition.plot_style import apply_manuscript_style, save_manuscript_figure
from heatwave_definition.raw_copernicus import rank_daily_cells_by_hwmid
from heatwave_definition.raw_eobs import load_eobs_tx_country_cells, rank_eobs_tx_files
from heatwave_definition.raw_era5 import rank_era5_t2m_directory


REPO = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = REPO / "outputs" / "reviewer_revision" / "threshold_sensitivity"
DEFAULT_FIGURE_DIR = REPO / "outputs" / "reviewer_revision" / "figures"
DATASET_COLORS = {"E-OBS": "#000000", "ERA5": "#009E73"}
DATASET_MARKERS = {"E-OBS": "o", "ERA5": "D"}


def main() -> None:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    args.figure_dir.mkdir(parents=True, exist_ok=True)

    core = None
    if args.core_dir is not None:
        core_files = sorted(args.core_dir.glob(args.core_pattern))
        if not core_files:
            raise FileNotFoundError(f"No CORe files found in {args.core_dir}")
        core_tmax, core_dates, _lat, _lon, core_mask = load_eobs_tx_country_cells(
            core_files,
            countries=args.countries,
            variable=args.core_variable,
            temperature_unit="K",
        )
        # CORe is updated in near real time; freeze it at the same cutoff as ERA5.
        selected = (core_dates.year >= args.start_year) & (core_dates <= pd.Timestamp(args.current_cutoff))
        core = (core_tmax[selected], pd.DatetimeIndex(core_dates[selected]), int(core_mask.sum()))

    frames = []
    for quantile in args.quantiles:
        eobs, _ = rank_eobs_tx_files(
            [args.eobs_file],
            countries=args.countries,
            top_years=args.top_years,
            ref_period=tuple(args.reference_period),
            min_heatwave_days=args.min_heatwave_days,
            threshold_quantile=quantile,
        )
        frames.append(label_ranking(eobs, "E-OBS", quantile))

        era5 = rank_era5_t2m_directory(
            args.era5_dir,
            countries=args.countries,
            top_years=args.top_years,
            ref_period=tuple(args.reference_period),
            min_heatwave_days=args.min_heatwave_days,
            threshold_quantile=quantile,
            start_year=args.start_year,
        )
        frames.append(label_ranking(era5, "ERA5", quantile))

        if core is not None:
            core_tmax, core_dates, core_cells = core
            core_ranking = rank_daily_cells_by_hwmid(
                core_tmax,
                core_dates,
                top_years=args.top_years,
                ref_period=tuple(args.reference_period),
                min_heatwave_days=args.min_heatwave_days,
                threshold_quantile=quantile,
            )
            core_ranking["country_cells"] = core_cells
            core_ranking["period_end"] = core_dates.max().date().isoformat()
            frames.append(label_ranking(core_ranking, "NOAA CORe", quantile))

    rankings = pd.concat(frames, ignore_index=True)
    rankings_path = args.output_dir / "threshold_quantile_top_years.csv"
    rankings.to_csv(rankings_path, index=False)

    top2 = rankings[rankings["rank"] <= 2].copy()
    top2["gap_to_rank_1_percent"] = top2.groupby(
        ["dataset", "threshold_quantile"]
    )["hwmid_sum"].transform(lambda values: 100.0 * (values.max() - values) / values.max())
    top2_path = args.output_dir / "threshold_quantile_top2_summary.csv"
    top2.to_csv(top2_path, index=False)

    figure_path = args.figure_dir / "threshold_quantile_sensitivity.png"
    plot_top2(top2, figure_path)
    print(rankings_path)
    print(top2_path)
    print(figure_path)


def label_ranking(ranking: pd.DataFrame, dataset: str, quantile: float) -> pd.DataFrame:
    result = ranking.copy()
    result.insert(0, "dataset", dataset)
    result.insert(1, "threshold_quantile", quantile)
    result.insert(2, "threshold_percentile", int(round(100 * quantile)))
    return result


def plot_top2(top2: pd.DataFrame, output: Path) -> None:
    apply_manuscript_style()
    fig, axes = plt.subplots(1, 2, figsize=(8.2, 3.5), sharey=False, constrained_layout=True)

    for ax, dataset in zip(axes, ["E-OBS", "ERA5"]):
        subset = top2[top2["dataset"] == dataset]
        for rank, linestyle in [(1, "-"), (2, "--")]:
            ranked = subset[subset["rank"] == rank].sort_values("threshold_percentile")
            ax.plot(
                ranked["threshold_percentile"],
                ranked["hwmid_sum"],
                color=DATASET_COLORS[dataset],
                marker=DATASET_MARKERS[dataset],
                linestyle=linestyle,
                linewidth=1.6,
                markersize=5.5,
                label=f"Rank {rank}",
            )
            for row in ranked.itertuples():
                ax.annotate(
                    str(int(row.year)),
                    (row.threshold_percentile, row.hwmid_sum),
                    xytext=(0, 7 if rank == 1 else -12),
                    textcoords="offset points",
                    ha="center",
                    fontsize=7.8,
                )
        ax.set_title(dataset)
        ax.set_xlabel("Temperature threshold percentile")
        ax.set_xticks(sorted(subset["threshold_percentile"].unique()))
        ax.grid(axis="y", color="#D9D9D9", linewidth=0.7)
        ax.spines[["top", "right"]].set_visible(False)

    axes[0].set_ylabel("Spatially aggregated annual HWMId score")
    axes[1].legend(frameon=False, loc="upper right")
    fig.suptitle("Sensitivity of the two highest-ranked heatwave years")
    save_manuscript_figure(fig, output)
    plt.close(fig)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("eobs_file", type=Path)
    parser.add_argument("era5_dir", type=Path)
    parser.add_argument("--core-dir", type=Path, help="Optional NOAA CORe directory (table output only)")
    parser.add_argument("--core-pattern", default="core_t2m_max_europe_*.nc")
    parser.add_argument("--core-variable", default="TMP_2maboveground")
    parser.add_argument("--start-year", type=int, default=1950)
    parser.add_argument("--current-cutoff", default="2026-07-01")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--figure-dir", type=Path, default=DEFAULT_FIGURE_DIR)
    parser.add_argument("--countries", nargs="+", default=["Germany", "France"])
    parser.add_argument("--reference-period", type=int, nargs=2, default=[1981, 2010])
    parser.add_argument("--quantiles", type=float, nargs="+", default=[0.90, 0.95, 0.99])
    parser.add_argument("--min-heatwave-days", type=int, default=3)
    parser.add_argument("--top-years", type=int, default=10)
    return parser.parse_args()


if __name__ == "__main__":
    main()
