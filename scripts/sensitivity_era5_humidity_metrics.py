"""Compare temperature and humidity-aware ERA5 heatwave-year rankings."""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
import netCDF4 as nc
import numpy as np
import pandas as pd

from heatwave_definition.humidity import (
    humidex_from_temperature_and_dewpoint,
    shade_wbgt_proxy,
    wet_bulb_temperature_stull,
)
from heatwave_definition.io import _decode_time, _first_existing_variable
from heatwave_definition.plot_style import apply_manuscript_style, save_manuscript_figure
from heatwave_definition.raw_copernicus import rank_daily_cells_by_hwmid
from heatwave_definition.regions import classify_countries_matrix


METRICS = [
    "Temperature-only HWMId",
    "Humidex-based event score",
    "Wet-bulb event score",
    "Shade-WBGT event score",
]
METRIC_COLORS = {
    "Temperature-only HWMId": "#0072B2",
    "Humidex-based event score": "#D55E00",
    "Wet-bulb event score": "#009E73",
    "Shade-WBGT event score": "#CC79A7",
}
METRIC_LABELS = {
    "Temperature-only HWMId": "Temperature only",
    "Humidex-based event score": "Humidex-based",
    "Wet-bulb event score": "Wet-bulb-based",
    "Shade-WBGT event score": "Shade-WBGT proxy",
}


def main() -> None:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    daily_metrics, dates = load_daily_metrics(
        args.temperature_dir,
        args.dewpoint_dir,
        args.start_year,
        args.end_year,
        args.countries,
        pd.Timestamp(args.current_cutoff),
    )

    periods = {
        "completed_1981_2025": pd.Timestamp("2025-12-31"),
        "including_2026": pd.Timestamp(args.current_cutoff),
    }
    frames = []
    for period, cutoff in periods.items():
        selected = dates <= cutoff
        for metric, values in daily_metrics.items():
            ranking = rank_daily_cells_by_hwmid(
                values[selected],
                dates[selected],
                top_years=len(
                    np.unique(dates[selected].year[dates[selected].year >= args.rank_year_start])
                ),
                ref_period=tuple(args.reference_period),
                min_heatwave_days=args.min_heatwave_days,
                threshold_quantile=args.threshold_quantile,
                rank_year_start=args.rank_year_start,
            ).rename(columns={"hwmid_sum": "regional_event_score"})
            ranking = ranking.drop(columns="hwmid_method")
            ranking.insert(0, "metric", metric)
            ranking.insert(0, "comparison", period)
            frames.append(ranking)

    rankings = pd.concat(frames, ignore_index=True)
    rankings.to_csv(args.output_dir / "era5_humidity_metrics_all_ranks.csv", index=False)
    rankings[rankings["rank"] <= args.top_years].to_csv(
        args.output_dir / "era5_humidity_metrics_top10.csv",
        index=False,
    )
    summary = agreement_summary(rankings, args.top_years)
    summary.to_csv(args.output_dir / "era5_humidity_metrics_summary.csv", index=False)
    plot_rank_matrix(
        rankings,
        args.output_dir / "era5_humidity_metrics_top10_matrix.png",
        args.top_years,
    )
    print(summary.to_string(index=False))


def load_daily_metrics(
    temperature_dir: Path,
    dewpoint_dir: Path,
    start_year: int,
    end_year: int,
    countries: list[str],
    cutoff: pd.Timestamp,
) -> tuple[dict[str, np.ndarray], pd.DatetimeIndex]:
    metric_chunks = {metric: [] for metric in METRICS}
    date_chunks = []
    expected_latitude = None
    expected_longitude = None
    country_mask = None

    for year in range(start_year, end_year + 1):
        temperature_path = temperature_dir / f"t2m_era5_{year}.nc"
        dewpoint_path = dewpoint_dir / f"d2m_era5_{year}.nc"
        if not temperature_path.exists() or not dewpoint_path.exists():
            raise FileNotFoundError(f"Missing paired ERA5 files for {year}")

        with nc.Dataset(temperature_path) as temperature_ds, nc.Dataset(dewpoint_path) as dewpoint_ds:
            temperature_time = _decode_time(
                temperature_ds.variables[_first_existing_variable(temperature_ds, ("valid_time", "time"))]
            )
            dewpoint_time = _decode_time(
                dewpoint_ds.variables[_first_existing_variable(dewpoint_ds, ("valid_time", "time"))]
            )
            valid_time = temperature_time <= cutoff
            temperature_time = temperature_time[valid_time]
            if not temperature_time.equals(dewpoint_time[dewpoint_time <= cutoff]):
                raise ValueError(f"Hourly timestamps differ for {year}")

            d_lat = np.asarray(dewpoint_ds.variables[_first_existing_variable(dewpoint_ds, ("latitude", "lat"))][:])
            d_lon = np.asarray(dewpoint_ds.variables[_first_existing_variable(dewpoint_ds, ("longitude", "lon"))][:])
            t_lat = np.asarray(temperature_ds.variables[_first_existing_variable(temperature_ds, ("latitude", "lat"))][:])
            t_lon = np.asarray(temperature_ds.variables[_first_existing_variable(temperature_ds, ("longitude", "lon"))][:])
            lat_slice = matching_slice(t_lat, d_lat, "latitude")
            lon_slice = matching_slice(t_lon, d_lon, "longitude")

            if expected_latitude is None:
                expected_latitude = d_lat
                expected_longitude = d_lon
                country_mask = classify_countries_matrix(d_lat, d_lon, countries)
            elif not (np.array_equal(expected_latitude, d_lat) and np.array_equal(expected_longitude, d_lon)):
                raise ValueError(f"Dewpoint grid changed in {dewpoint_path}")

            t2m = np.ma.filled(
                temperature_ds.variables["t2m"][: len(temperature_time), lat_slice, lon_slice],
                np.nan,
            )[:, country_mask]
            d2m = np.ma.filled(
                dewpoint_ds.variables["d2m"][: len(temperature_time), :, :],
                np.nan,
            )[:, country_mask]
            hourly_humidex = humidex_from_temperature_and_dewpoint(t2m, d2m)
            hourly_wet_bulb = wet_bulb_temperature_stull(t2m, d2m)
            hourly_shade_wbgt = shade_wbgt_proxy(t2m, d2m)
            daily_dates, daily_tmax = daily_maximum(temperature_time, t2m - 273.15)
            humidex_dates, daily_humidex = daily_maximum(temperature_time, hourly_humidex)
            wet_bulb_dates, daily_wet_bulb = daily_maximum(temperature_time, hourly_wet_bulb)
            wbgt_dates, daily_shade_wbgt = daily_maximum(temperature_time, hourly_shade_wbgt)
            if not (
                daily_dates.equals(humidex_dates)
                and daily_dates.equals(wet_bulb_dates)
                and daily_dates.equals(wbgt_dates)
            ):
                raise ValueError(f"Daily aggregation differs for {year}")
            for metric, values in zip(
                METRICS,
                (daily_tmax, daily_humidex, daily_wet_bulb, daily_shade_wbgt),
            ):
                metric_chunks[metric].append(values.astype(np.float32))
            date_chunks.append(daily_dates)
            print(f"Loaded ERA5 temperature and dewpoint for {year}")

    return (
        {metric: np.vstack(chunks) for metric, chunks in metric_chunks.items()},
        pd.DatetimeIndex(np.concatenate([chunk.to_numpy() for chunk in date_chunks])),
    )


def matching_slice(container: np.ndarray, subset: np.ndarray, name: str) -> slice:
    positions = []
    for value in subset:
        matches = np.flatnonzero(np.isclose(container, value, atol=1e-6))
        if len(matches) != 1:
            raise ValueError(f"Could not match {name} coordinate {value}")
        positions.append(int(matches[0]))
    if positions != list(range(positions[0], positions[-1] + 1)):
        raise ValueError(f"Matched {name} coordinates are not contiguous")
    return slice(positions[0], positions[-1] + 1)


def daily_maximum(
    timestamps: pd.DatetimeIndex,
    hourly_values: np.ndarray,
) -> tuple[pd.DatetimeIndex, np.ndarray]:
    days = timestamps.floor("D")
    daily_dates = pd.DatetimeIndex(pd.unique(days))
    result = np.full((len(daily_dates), hourly_values.shape[1]), np.nan, dtype=np.float32)
    for index, day in enumerate(daily_dates):
        result[index] = np.nanmax(hourly_values[days == day], axis=0)
    return daily_dates, result


def agreement_summary(rankings: pd.DataFrame, top_years: int) -> pd.DataFrame:
    rows = []
    for comparison, subset in rankings.groupby("comparison", sort=False):
        rank_pivot = subset.pivot(index="year", columns="metric", values="rank")
        score_pivot = subset.pivot(index="year", columns="metric", values="regional_event_score")
        temperature_top = set(rank_pivot.index[rank_pivot[METRICS[0]] <= top_years])
        for metric in METRICS[1:]:
            metric_top = set(rank_pivot.index[rank_pivot[metric] <= top_years])
            row = {
                "comparison": comparison,
                "comparison_metric": metric,
                "spearman_vs_temperature": rank_pivot[[METRICS[0], metric]]
                .corr(method="spearman")
                .iloc[0, 1],
                "common_top10_years": len(temperature_top & metric_top),
            }
            for year in (2003, 2026):
                row[f"temperature_rank_{year}"] = (
                    int(rank_pivot.loc[year, METRICS[0]])
                    if year in rank_pivot.index
                    else np.nan
                )
                row[f"metric_rank_{year}"] = (
                    int(rank_pivot.loc[year, metric]) if year in rank_pivot.index else np.nan
                )
            if 2003 in score_pivot.index and 2026 in score_pivot.index:
                row["temperature_2026_vs_2003_percent"] = (
                    100.0 * score_pivot.loc[2026, METRICS[0]] / score_pivot.loc[2003, METRICS[0]]
                )
                row["metric_2026_vs_2003_percent"] = (
                    100.0 * score_pivot.loc[2026, metric] / score_pivot.loc[2003, metric]
                )
            rows.append(row)
    return pd.DataFrame(rows)


def plot_rank_matrix(rankings: pd.DataFrame, output: Path, top_years: int) -> None:
    apply_manuscript_style()
    fig, axes = plt.subplots(1, 2, figsize=(12.2, 5.15))
    panels = [
        ("completed_1981_2025", "A  Completed years (1981-2025)"),
        ("including_2026", "B  Including 2026 (through 1 July)"),
    ]
    for axis, (comparison, title) in zip(axes, panels):
        subset = rankings[
            (rankings["comparison"] == comparison) & (rankings["rank"] <= top_years)
        ]
        for row_index, metric in enumerate(METRICS):
            rows = subset[subset["metric"] == metric].set_index("rank")
            for rank in range(1, top_years + 1):
                year = int(rows.loc[rank, "year"])
                face = "#F2F2F2"
                text_color = "#26364A"
                if year == 2003:
                    face, text_color = "#B2182B", "white"
                elif year == 2026:
                    face, text_color = "#E69F00", "#17202A"
                axis.add_patch(
                    Rectangle(
                        (rank - 0.43, row_index - 0.34),
                        0.86,
                        0.68,
                        facecolor=face,
                        edgecolor=METRIC_COLORS[metric],
                        linewidth=1.2,
                    )
                )
                axis.text(
                    rank,
                    row_index,
                    str(year),
                    ha="center",
                    va="center",
                    color=text_color,
                    fontweight="bold" if year in (2003, 2026) else "normal",
                    fontsize=8.1,
                )
        axis.set_xlim(0.45, top_years + 0.55)
        axis.set_ylim(len(METRICS) - 0.45, -0.55)
        axis.set_xticks(range(1, top_years + 1))
        axis.set_yticks(range(len(METRICS)), [METRIC_LABELS[metric] for metric in METRICS])
        axis.set_xlabel("Rank")
        axis.set_title(title, loc="left", pad=14)
        for spine in axis.spines.values():
            spine.set_visible(False)
        axis.tick_params(axis="both", length=0)
    fig.suptitle("Does humidity change the selection of ERA5 heatwave years?", y=0.97)
    fig.text(
        0.5,
        0.035,
        "Red: 2003 benchmark. Orange: incomplete 2026. Each row is ranked separately using identical percentile, duration and aggregation rules.",
        ha="center",
        color="#666666",
        fontsize=8.5,
    )
    fig.subplots_adjust(left=0.12, right=0.985, bottom=0.16, top=0.82, wspace=0.31)
    save_manuscript_figure(fig, output)
    plt.close(fig)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("temperature_dir", type=Path)
    parser.add_argument("dewpoint_dir", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--start-year", type=int, default=1980)
    parser.add_argument("--rank-year-start", type=int, default=1981)
    parser.add_argument("--end-year", type=int, default=2026)
    parser.add_argument("--current-cutoff", default="2026-07-01 23:00:00")
    parser.add_argument("--countries", nargs="+", default=["Germany", "France"])
    parser.add_argument("--reference-period", type=int, nargs=2, default=[1981, 2010])
    parser.add_argument("--threshold-quantile", type=float, default=0.90)
    parser.add_argument("--min-heatwave-days", type=int, default=3)
    parser.add_argument("--top-years", type=int, default=10)
    return parser.parse_args()


if __name__ == "__main__":
    main()
