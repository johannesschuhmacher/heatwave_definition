"""Compare E-OBS, ERA5 and NOAA CORe HWMId rankings on synchronized periods."""

from __future__ import annotations

import argparse
from itertools import combinations
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
import numpy as np
import pandas as pd

from heatwave_definition.plot_style import apply_manuscript_style, save_manuscript_figure
from heatwave_definition.raw_copernicus import rank_daily_cells_by_hwmid
from heatwave_definition.raw_eobs import load_eobs_tx_country_cells
from heatwave_definition.raw_era5 import (
    filter_files_by_year,
    load_era5_t2m_country_cells,
)


REPO = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = REPO / "outputs" / "reviewer_revision" / "reanalysis_comparison"
PRODUCTS = ["E-OBS", "ERA5", "NOAA CORe"]
PRODUCT_COLORS = {"E-OBS": "#000000", "ERA5": "#009E73", "NOAA CORe": "#0072B2"}
PRODUCT_MARKERS = {"E-OBS": "s", "ERA5": "D", "NOAA CORe": "o"}
PRODUCT_LABELS = {"E-OBS": "E-OBS (through 2025)", "ERA5": "ERA5", "NOAA CORe": "NOAA CORe"}
PERIOD_LABELS = {
    "completed_1950_2025": "Completed years (1950-2025)",
    "including_2026": "Including 2026 (through 1 July)",
}


def main() -> None:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    era5_files = filter_files_by_year(
        sorted(args.era5_dir.glob(args.era5_pattern)),
        start_year=args.start_year,
        end_year=args.current_cutoff.year,
    )
    core_files = sorted(args.core_dir.glob(args.core_pattern))
    if not era5_files:
        raise FileNotFoundError(f"No ERA5 files found in {args.era5_dir}")
    if not core_files:
        raise FileNotFoundError(f"No CORe files found in {args.core_dir}")

    era5_tmax, era5_dates, era5_mask = load_era5_t2m_country_cells(
        era5_files,
        countries=args.countries,
    )
    core_tmax, core_dates, _lat, _lon, core_mask = load_eobs_tx_country_cells(
        core_files,
        countries=args.countries,
        variable=args.core_variable,
        temperature_unit="K",
    )
    eobs_tmax, eobs_dates, _lat, _lon, eobs_mask = load_eobs_tx_country_cells(
        [args.eobs_file],
        countries=args.countries,
        variable=args.eobs_variable,
        temperature_unit="degC",
    )
    products = {
        "E-OBS": (eobs_tmax, eobs_dates, int(eobs_mask.sum())),
        "ERA5": (era5_tmax, era5_dates, int(era5_mask.sum())),
        "NOAA CORe": (core_tmax, core_dates, int(core_mask.sum())),
    }

    periods = {
        "completed_1950_2025": pd.Timestamp(args.completed_end),
        "including_2026": pd.Timestamp(args.current_cutoff),
    }
    ranking_frames = []
    coverage_rows = []
    for period, cutoff in periods.items():
        for product, (daily_tmax, dates, country_cells) in products.items():
            product_cutoff = min(cutoff, dates.max())
            period_tmax, period_dates = select_period(
                daily_tmax,
                dates,
                pd.Timestamp(args.start_year, 1, 1),
                product_cutoff,
            )
            year_count = len(period_dates.year.unique())
            ranking = rank_daily_cells_by_hwmid(
                period_tmax,
                period_dates,
                top_years=year_count,
                ref_period=tuple(args.reference_period),
                min_heatwave_days=args.min_heatwave_days,
                threshold_quantile=args.threshold_quantile,
            )
            ranking.insert(0, "product", product)
            ranking.insert(0, "comparison", period)
            ranking["country_cells"] = country_cells
            ranking["period_end"] = product_cutoff.date().isoformat()
            ranking["includes_2026"] = bool(2026 in period_dates.year)
            ranking_frames.append(ranking)
            coverage_rows.append(
                coverage_row(period, product, period_dates, product_cutoff)
            )

    rankings = pd.concat(ranking_frames, ignore_index=True)
    rankings.to_csv(args.output_dir / "reanalysis_all_year_ranks.csv", index=False)
    rankings[rankings["rank"] <= args.top_years].to_csv(
        args.output_dir / "reanalysis_top10_rankings.csv",
        index=False,
    )
    coverage = pd.DataFrame(coverage_rows)
    coverage.to_csv(args.output_dir / "reanalysis_period_coverage.csv", index=False)

    differences = build_rank_differences(rankings)
    differences.to_csv(args.output_dir / "reanalysis_rank_differences.csv", index=False)
    summary = build_agreement_summary(differences, rankings, args.top_years)
    summary.to_csv(args.output_dir / "reanalysis_agreement_summary.csv", index=False)
    pairwise = build_pairwise_agreement(rankings, args.top_years)
    pairwise.to_csv(args.output_dir / "historical_product_pairwise_agreement.csv", index=False)

    figure_path = args.output_dir / "reanalysis_rank_comparison_with_without_2026.png"
    plot_rank_comparison(differences, figure_path, args.top_years)
    matrix_path = args.output_dir / "historical_product_top10_matrix_with_without_2026.png"
    plot_rank_matrix(rankings, matrix_path, args.top_years)

    print(args.output_dir / "reanalysis_top10_rankings.csv")
    print(args.output_dir / "reanalysis_agreement_summary.csv")
    print(args.output_dir / "reanalysis_period_coverage.csv")
    print(args.output_dir / "historical_product_pairwise_agreement.csv")
    print(figure_path)
    print(matrix_path)
    print(summary.to_string(index=False))


def select_period(
    daily_tmax: np.ndarray,
    dates: pd.DatetimeIndex,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> tuple[np.ndarray, pd.DatetimeIndex]:
    mask = (dates >= start) & (dates <= end)
    return daily_tmax[mask, :], pd.DatetimeIndex(dates[mask])


def coverage_row(
    comparison: str,
    product: str,
    dates: pd.DatetimeIndex,
    cutoff: pd.Timestamp,
) -> dict[str, object]:
    expected = pd.date_range(dates.min(), cutoff, freq="D")
    missing = expected.difference(dates)
    return {
        "comparison": comparison,
        "product": product,
        "first_date": dates.min().date().isoformat(),
        "last_date": dates.max().date().isoformat(),
        "daily_steps": len(dates),
        "missing_days": len(missing),
        "missing_dates": ";".join(value.date().isoformat() for value in missing),
    }


def build_rank_differences(rankings: pd.DataFrame) -> pd.DataFrame:
    pivot = rankings.pivot(index=["comparison", "year"], columns="product", values="rank")
    pivot = pivot.reset_index()
    pivot["rank_difference_core_minus_era5"] = pivot["NOAA CORe"] - pivot["ERA5"]
    return pivot


def build_pairwise_agreement(rankings: pd.DataFrame, top_years: int) -> pd.DataFrame:
    rows = []
    for comparison, period_rankings in rankings.groupby("comparison", sort=False):
        for left, right in combinations(PRODUCTS, 2):
            left_rows = period_rankings[period_rankings["product"] == left]
            right_rows = period_rankings[period_rankings["product"] == right]
            merged = left_rows[["year", "rank"]].merge(
                right_rows[["year", "rank"]],
                on="year",
                suffixes=("_left", "_right"),
            )
            left_top = set(left_rows.loc[left_rows["rank"] <= top_years, "year"])
            right_top = set(right_rows.loc[right_rows["rank"] <= top_years, "year"])
            common_top = sorted(left_top & right_top)
            left_end = str(left_rows["period_end"].iloc[0])
            right_end = str(right_rows["period_end"].iloc[0])
            rows.append(
                {
                    "comparison": comparison,
                    "product_1": left,
                    "product_2": right,
                    "same_period_end": left_end == right_end,
                    "product_1_period_end": left_end,
                    "product_2_period_end": right_end,
                    "common_year_count": len(merged),
                    "rank_correlation_common_years": np.corrcoef(
                        merged["rank_left"], merged["rank_right"]
                    )[0, 1],
                    "common_top10_count": len(common_top),
                    "top10_jaccard_index": len(common_top) / len(left_top | right_top),
                    "common_top10_years": "+".join(map(str, common_top)),
                }
            )
    return pd.DataFrame(rows)


def build_agreement_summary(
    differences: pd.DataFrame,
    rankings: pd.DataFrame,
    top_years: int,
) -> pd.DataFrame:
    rows = []
    for comparison, subset in differences.groupby("comparison", sort=False):
        era5_top2 = set(subset.loc[subset["ERA5"] <= 2, "year"])
        core_top2 = set(subset.loc[subset["NOAA CORe"] <= 2, "year"])
        period_rankings = rankings[rankings["comparison"] == comparison]
        era5_ordered_top2 = ordered_top_years(period_rankings, "ERA5", 2)
        core_ordered_top2 = ordered_top_years(period_rankings, "NOAA CORe", 2)
        era5_top = set(subset.loc[subset["ERA5"] <= top_years, "year"])
        core_top = set(subset.loc[subset["NOAA CORe"] <= top_years, "year"])
        top_common = sorted(era5_top & core_top)
        ranks_2003 = subset.loc[subset["year"] == 2003].iloc[0]
        ranks_2026 = subset.loc[subset["year"] == 2026]
        rows.append(
            {
                "comparison": comparison,
                "rank_correlation_all_years": np.corrcoef(
                    subset["ERA5"], subset["NOAA CORe"]
                )[0, 1],
                "mean_absolute_rank_difference": np.mean(
                    np.abs(subset["rank_difference_core_minus_era5"])
                ),
                "same_top2_set": era5_top2 == core_top2,
                "same_ordered_top2": era5_ordered_top2 == core_ordered_top2,
                "common_top2_years": "+".join(map(str, sorted(era5_top2 & core_top2))),
                "common_top10_count": len(top_common),
                "top10_jaccard_index": len(top_common) / len(era5_top | core_top),
                "common_top10_years": "+".join(map(str, top_common)),
                "era5_rank_2003": int(ranks_2003["ERA5"]),
                "core_rank_2003": int(ranks_2003["NOAA CORe"]),
                "era5_rank_2026": rank_or_missing(ranks_2026, "ERA5"),
                "core_rank_2026": rank_or_missing(ranks_2026, "NOAA CORe"),
                "era5_2026_vs_2003_percent": score_ratio_percent(
                    period_rankings, "ERA5", 2026, 2003
                ),
                "core_2026_vs_2003_percent": score_ratio_percent(
                    period_rankings, "NOAA CORe", 2026, 2003
                ),
            }
        )
    return pd.DataFrame(rows)


def rank_or_missing(rows: pd.DataFrame, column: str):
    return pd.NA if rows.empty else int(rows.iloc[0][column])


def ordered_top_years(rankings: pd.DataFrame, product: str, count: int) -> tuple[int, ...]:
    rows = rankings[rankings["product"] == product].nsmallest(count, "rank")
    return tuple(rows["year"].astype(int))


def score_ratio_percent(
    rankings: pd.DataFrame,
    product: str,
    numerator_year: int,
    denominator_year: int,
):
    rows = rankings[rankings["product"] == product].set_index("year")
    if numerator_year not in rows.index or denominator_year not in rows.index:
        return pd.NA
    return 100.0 * rows.loc[numerator_year, "hwmid_sum"] / rows.loc[denominator_year, "hwmid_sum"]


def plot_rank_comparison(differences: pd.DataFrame, output: Path, top_years: int) -> None:
    apply_manuscript_style()
    comparisons = list(PERIOD_LABELS)
    fig, axes = plt.subplots(1, 2, figsize=(10.6, 6.4))
    for panel, (axis, comparison) in enumerate(zip(axes, comparisons), start=1):
        subset = differences[differences["comparison"] == comparison].copy()
        subset = subset[
            (subset["ERA5"] <= top_years) | (subset["NOAA CORe"] <= top_years)
        ]
        subset["best_rank"] = subset[["ERA5", "NOAA CORe"]].min(axis=1)
        subset = subset.sort_values(["best_rank", "year"]).reset_index(drop=True)
        y_positions = np.arange(len(subset))
        for position, (_, row) in zip(y_positions, subset.iterrows()):
            ranks = row[PRODUCTS].dropna().to_numpy(dtype=float)
            axis.plot(
                [ranks.min(), ranks.max()],
                [position, position],
                color="#B8B8B8",
                linewidth=1.0,
                zorder=1,
            )
        for product in PRODUCTS:
            available = subset[product].notna()
            axis.scatter(
                subset.loc[available, product],
                y_positions[available],
                color=PRODUCT_COLORS[product],
                marker=PRODUCT_MARKERS[product],
                s=38,
                label=PRODUCT_LABELS[product],
                zorder=2,
            )
        labels = [f"{int(year)}*" if year == 2026 else str(int(year)) for year in subset["year"]]
        axis.set_yticks(y_positions, labels)
        axis.invert_yaxis()
        axis.set_xlabel("Rank within data product")
        axis.set_title(f"{chr(64 + panel)}  {PERIOD_LABELS[comparison]}", loc="left")
        maximum_rank = int(np.nanmax(subset[PRODUCTS].to_numpy(dtype=float)))
        axis.set_xlim(0.5, max(12, maximum_rank + 1))
        axis.set_xticks(range(1, int(axis.get_xlim()[1]) + 1, 2))
        axis.grid(axis="x", color="#E0E0E0", linewidth=0.7)
        axis.spines[["top", "right", "left"]].set_visible(False)
        axis.tick_params(axis="y", length=0)

    handles, labels = axes[0].get_legend_handles_labels()
    fig.subplots_adjust(left=0.08, right=0.98, bottom=0.13, top=0.82, wspace=0.12)
    fig.legend(handles, labels, loc="upper center", ncol=2, frameon=False, bbox_to_anchor=(0.5, 0.90))
    fig.suptitle("Sensitivity of heatwave-year rankings to the historical data product", y=0.975)
    fig.text(
        0.5,
        0.035,
        "Years shown are in the top 10 of at least one product. *2026 is incomplete and "
        "unavailable in E-OBS; absolute HWMId sums are not compared across native grids.",
        ha="center",
        fontsize=8.2,
        color="#555555",
    )
    save_manuscript_figure(fig, output)
    plt.close(fig)


def plot_rank_matrix(rankings: pd.DataFrame, output: Path, top_years: int) -> None:
    apply_manuscript_style()
    comparisons = list(PERIOD_LABELS)
    fig, axes = plt.subplots(1, 2, figsize=(12.0, 4.0))
    panel_messages = {
        "completed_1950_2025": "All three products rank 2003 first",
        "including_2026": "Both reanalyses rank 2026 second",
    }

    for panel, (axis, comparison) in enumerate(zip(axes, comparisons), start=1):
        subset = rankings[
            (rankings["comparison"] == comparison) & (rankings["rank"] <= top_years)
        ]
        for row, product in enumerate(PRODUCTS):
            product_rows = subset[subset["product"] == product].set_index("rank")
            for rank in range(1, top_years + 1):
                year = int(product_rows.loc[rank, "year"])
                facecolor, textcolor = matrix_cell_colors(year)
                axis.add_patch(
                    Rectangle(
                        (rank - 0.43, row - 0.34),
                        0.86,
                        0.68,
                        facecolor=facecolor,
                        edgecolor=PRODUCT_COLORS[product],
                        linewidth=1.0,
                    )
                )
                axis.text(
                    rank,
                    row,
                    str(year),
                    ha="center",
                    va="center",
                    fontsize=7.7,
                    color=textcolor,
                    fontweight="bold" if year in (2003, 2026) else "normal",
                )

        y_labels = ["E-OBS", "ERA5", "NOAA\nCORe"]
        if comparison == "including_2026":
            y_labels[0] = "E-OBS*"
        axis.set_xlim(0.45, top_years + 0.55)
        axis.set_ylim(len(PRODUCTS) - 0.5, -0.5)
        axis.set_xticks(range(1, top_years + 1))
        axis.set_yticks(range(len(PRODUCTS)), y_labels)
        axis.set_xlabel("Rank")
        axis.set_title(f"{chr(64 + panel)}  {PERIOD_LABELS[comparison]}", loc="left", pad=22)
        axis.text(
            0.0,
            1.04,
            panel_messages[comparison],
            transform=axis.transAxes,
            ha="left",
            va="bottom",
            fontsize=8.7,
            color="#555555",
        )
        axis.tick_params(axis="both", length=0)
        axis.spines[:].set_visible(False)

    fig.subplots_adjust(left=0.09, right=0.985, bottom=0.22, top=0.74, wspace=0.25)
    fig.suptitle("Top-ranked heatwave years across historical data products", y=0.96)
    fig.text(
        0.5,
        0.07,
        "Red: 2003 benchmark. Orange: incomplete 2026. *E-OBS is available only "
        "through 2025; HWMId sums are not compared across native grids.",
        ha="center",
        fontsize=8.2,
        color="#555555",
    )
    save_manuscript_figure(fig, output)
    plt.close(fig)


def matrix_cell_colors(year: int) -> tuple[str, str]:
    if year == 2003:
        return "#B2182B", "white"
    if year == 2026:
        return "#E69F00", "#172033"
    return "#F4F4F4", "#172033"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("era5_dir", type=Path)
    parser.add_argument("core_dir", type=Path)
    parser.add_argument("eobs_file", type=Path)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--era5-pattern", default="t2m_era5_*.nc")
    parser.add_argument("--core-pattern", default="core_t2m_max_europe_*.nc")
    parser.add_argument("--core-variable", default="TMP_2maboveground")
    parser.add_argument("--eobs-variable", default="tx")
    parser.add_argument("--countries", nargs="+", default=["Germany", "France"])
    parser.add_argument("--reference-period", type=int, nargs=2, default=[1981, 2010])
    parser.add_argument("--threshold-quantile", type=float, default=0.90)
    parser.add_argument("--min-heatwave-days", type=int, default=3)
    parser.add_argument("--top-years", type=int, default=10)
    parser.add_argument("--start-year", type=int, default=1950)
    parser.add_argument("--completed-end", type=pd.Timestamp, default=pd.Timestamp("2025-12-31"))
    parser.add_argument("--current-cutoff", type=pd.Timestamp, default=pd.Timestamp("2026-07-01"))
    return parser.parse_args()


if __name__ == "__main__":
    main()
