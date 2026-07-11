"""Analyze an ERA5 heatwave event against an HWMId reference period."""

from __future__ import annotations

import argparse
import re
from pathlib import Path

import netCDF4 as nc
import numpy as np
import pandas as pd

from heatwave_definition.hwmid import _build_threshold_masks, _find_runs
from heatwave_definition.io import _decode_time, _first_existing_variable
from heatwave_definition.raw_copernicus import _load_daily_tmax_for_mask, rank_daily_cells_by_hwmid
from heatwave_definition.regions import classify_countries_matrix


REPO = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = REPO / "outputs" / "era5_current_heatwave"


def main() -> None:
    args = parse_args()
    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    files = select_files(
        args.input_dir,
        ref_period=(args.reference_period[0], args.reference_period[1]),
        event_year=args.event_start.year,
        include_years=args.include_years,
        require_boundary_years=not args.allow_missing_boundary_years,
    )
    daily_tmax, dates, cell_lat, cell_lon = load_country_cells(
        files,
        countries=args.countries,
        variable=args.variable,
        temperature_unit=args.temperature_unit,
    )

    ranking = rank_daily_cells_by_hwmid(
        daily_tmax=daily_tmax,
        dates=dates,
        top_years=args.top_years,
        ref_period=(args.reference_period[0], args.reference_period[1]),
        min_heatwave_days=args.min_heatwave_days,
        threshold_quantile=args.threshold_quantile,
    )
    ranking_path = output_dir / "era5_de_fr_available_year_ranking.csv"
    ranking.to_csv(ranking_path, index=False)

    event_summary, daily_summary, cell_events = analyze_event(
        daily_tmax=daily_tmax,
        dates=dates,
        cell_lat=cell_lat,
        cell_lon=cell_lon,
        ref_period=(args.reference_period[0], args.reference_period[1]),
        event_start=pd.Timestamp(args.event_start),
        event_end=pd.Timestamp(args.event_end),
        min_heatwave_days=args.min_heatwave_days,
        threshold_quantile=args.threshold_quantile,
    )
    event_summary["countries"] = "+".join(args.countries)
    event_summary["source_file_count"] = len(files)
    event_summary["source_files"] = ";".join(path.name for path in files)

    event_summary_path = output_dir / "era5_de_fr_2026_june_event_summary.csv"
    daily_summary_path = output_dir / "era5_de_fr_2026_june_daily_summary.csv"
    cell_events_path = output_dir / "era5_de_fr_2026_june_cell_events.csv"
    event_summary.to_csv(event_summary_path, index=False)
    daily_summary.to_csv(daily_summary_path, index=False)
    cell_events.to_csv(cell_events_path, index=False)

    print(f"Ranking: {ranking_path}")
    print(ranking.to_string(index=False))
    print(f"Event summary: {event_summary_path}")
    print(event_summary.to_string(index=False))
    print(f"Daily summary: {daily_summary_path}")
    print(f"Cell events: {cell_events_path}")


def select_files(
    input_dir: Path,
    ref_period: tuple[int, int],
    event_year: int,
    include_years: list[int],
    require_boundary_years: bool,
) -> list[Path]:
    available = {}
    for path in input_dir.glob("t2m_era5_*.nc"):
        match = re.search(r"t2m_era5_(\d{4})\.nc$", path.name)
        if match:
            available[int(match.group(1))] = path

    years = set(range(ref_period[0], ref_period[1] + 1))
    years.update(include_years)
    years.add(event_year)
    boundary_years = {ref_period[0] - 1, ref_period[1] + 1}
    if require_boundary_years:
        years.update(boundary_years)
    else:
        years.update(year for year in boundary_years if year in available)

    missing = sorted(year for year in years if year not in available)
    if missing:
        raise FileNotFoundError(f"Missing ERA5 years for exact analysis: {missing}")
    return [available[year] for year in sorted(years)]


def load_country_cells(
    files: list[Path],
    countries: list[str],
    variable: str,
    temperature_unit: str,
) -> tuple[np.ndarray, pd.DatetimeIndex, np.ndarray, np.ndarray]:
    daily_chunks = []
    date_chunks = []
    latitude = None
    longitude = None
    mask = None
    cell_lat = None
    cell_lon = None

    for path in files:
        with nc.Dataset(path, "r") as dataset:
            time_name = _first_existing_variable(dataset, ("valid_time", "time"))
            latitude_name = _first_existing_variable(dataset, ("latitude", "lat"))
            longitude_name = _first_existing_variable(dataset, ("longitude", "lon"))
            dates_hourly = _decode_time(dataset.variables[time_name])
            day_index = dates_hourly.floor("D")
            daily_dates = pd.DatetimeIndex(pd.unique(day_index))
            file_latitude = np.asarray(dataset.variables[latitude_name][:])
            file_longitude = np.asarray(dataset.variables[longitude_name][:])

            if latitude is None:
                latitude = file_latitude
                longitude = file_longitude
                mask = classify_countries_matrix(latitude, longitude, countries)
                lon_grid, lat_grid = np.meshgrid(longitude, latitude)
                cell_lat = lat_grid[mask]
                cell_lon = lon_grid[mask]
            elif not (np.array_equal(latitude, file_latitude) and np.array_equal(longitude, file_longitude)):
                raise ValueError(f"Grid coordinates changed in {path}")

            daily_chunks.append(
                _load_daily_tmax_for_mask(
                    dataset.variables[variable],
                    dates_hourly,
                    day_index,
                    daily_dates,
                    mask,
                    temperature_unit=temperature_unit,
                )
            )
            date_chunks.append(daily_dates)

    daily_tmax = np.vstack(daily_chunks)
    dates = pd.DatetimeIndex(np.concatenate([chunk.to_numpy() for chunk in date_chunks]))
    order = np.argsort(dates.to_numpy())
    return daily_tmax[order, :], pd.DatetimeIndex(dates.to_numpy()[order]), cell_lat, cell_lon


def analyze_event(
    daily_tmax: np.ndarray,
    dates: pd.DatetimeIndex,
    cell_lat: np.ndarray,
    cell_lon: np.ndarray,
    ref_period: tuple[int, int],
    event_start: pd.Timestamp,
    event_end: pd.Timestamp,
    min_heatwave_days: int,
    threshold_quantile: float,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    ref_years = list(range(ref_period[0], ref_period[1] + 1))
    threshold_masks = _build_threshold_masks(dates, ref_years)
    thresholds = np.full((366, daily_tmax.shape[1]), np.nan, dtype=np.float32)
    for day, idx in enumerate(threshold_masks):
        if len(idx):
            thresholds[day, :] = np.nanquantile(daily_tmax[idx, :], threshold_quantile, axis=0)

    ref_annual_max = np.vstack(
        [
            np.nanmax(
                daily_tmax[(dates >= pd.Timestamp(year, 1, 1)) & (dates <= pd.Timestamp(year, 12, 31)), :],
                axis=0,
            )
            for year in ref_years
        ]
    )
    t25 = np.nanquantile(ref_annual_max, 0.25, axis=0)
    denominator = np.nanquantile(ref_annual_max, 0.75, axis=0) - t25
    valid = np.isfinite(denominator) & (denominator > 0)

    day_of_year = dates.dayofyear.to_numpy()
    event_mask = (dates >= event_start) & (dates <= event_end)
    event_positions = np.where(event_mask)[0]
    if not len(event_positions):
        raise ValueError(f"No dates found between {event_start.date()} and {event_end.date()}")

    daily_rows = []
    cell_rows = []
    hwmid_by_cell = np.zeros(daily_tmax.shape[1], dtype=float)
    duration_by_cell = np.zeros(daily_tmax.shape[1], dtype=float)
    touched_by_cell = np.zeros(daily_tmax.shape[1], dtype=bool)
    qualifying_by_cell = np.zeros(daily_tmax.shape[1], dtype=bool)

    daily_thresholds = thresholds[day_of_year - 1, :]
    above = np.isfinite(daily_tmax) & (daily_tmax > daily_thresholds)
    daily_magnitude = np.where(
        (daily_tmax > t25[None, :]) & valid[None, :],
        (daily_tmax - t25[None, :]) / denominator[None, :],
        0.0,
    )
    daily_magnitude[~above] = 0.0

    for pos in event_positions:
        row_values = daily_tmax[pos, :]
        row_thresholds = daily_thresholds[pos, :]
        row_above = above[pos, :]
        daily_rows.append(
            {
                "date": dates[pos].date().isoformat(),
                "mean_tmax_c": float(np.nanmean(row_values)),
                "max_tmax_c": float(np.nanmax(row_values)),
                "mean_threshold_c": float(np.nanmean(row_thresholds)),
                "cells_above_threshold": int(np.count_nonzero(row_above)),
                "share_cells_above_threshold": float(np.count_nonzero(row_above) / daily_tmax.shape[1]),
                "daily_hwmid_sum": float(np.nansum(daily_magnitude[pos, :])),
            }
        )

    for cell in range(daily_tmax.shape[1]):
        if not valid[cell]:
            continue
        runs = _find_runs(above[:, cell], min_heatwave_days)
        for start_idx, end_idx in runs:
            overlaps_event = start_idx <= event_positions[-1] and end_idx >= event_positions[0]
            if not overlaps_event:
                continue
            overlap_start = max(start_idx, event_positions[0])
            overlap_end = min(end_idx, event_positions[-1])
            event_magnitude = float(np.nansum(daily_magnitude[overlap_start : overlap_end + 1, cell]))
            if event_magnitude <= 0:
                continue
            touched_by_cell[cell] = True
            qualifying_by_cell[cell] = True
            hwmid_by_cell[cell] += event_magnitude
            duration_by_cell[cell] += overlap_end - overlap_start + 1
            cell_rows.append(
                {
                    "lat": float(cell_lat[cell]),
                    "lon": float(cell_lon[cell]),
                    "event_start": dates[start_idx].date().isoformat(),
                    "event_end": dates[end_idx].date().isoformat(),
                    "overlap_start": dates[overlap_start].date().isoformat(),
                    "overlap_end": dates[overlap_end].date().isoformat(),
                    "overlap_days": int(overlap_end - overlap_start + 1),
                    "event_overlap_hwmid": event_magnitude,
                    "max_tmax_c_in_overlap": float(np.nanmax(daily_tmax[overlap_start : overlap_end + 1, cell])),
                    "max_daily_magnitude_in_overlap": float(np.nanmax(daily_magnitude[overlap_start : overlap_end + 1, cell])),
                }
            )

    event_summary = pd.DataFrame(
        [
            {
                "event_window_start": event_start.date().isoformat(),
                "event_window_end": event_end.date().isoformat(),
                "cell_count": int(daily_tmax.shape[1]),
                "qualifying_heatwave_cells": int(np.count_nonzero(qualifying_by_cell)),
                "share_qualifying_heatwave_cells": float(np.count_nonzero(qualifying_by_cell) / daily_tmax.shape[1]),
                "event_overlap_hwmid_sum": float(np.nansum(hwmid_by_cell)),
                "event_overlap_hwmid_mean_all_cells": float(np.nanmean(hwmid_by_cell)),
                "event_overlap_hwmid_mean_qualifying_cells": float(np.nanmean(hwmid_by_cell[qualifying_by_cell]))
                if qualifying_by_cell.any()
                else 0.0,
                "mean_overlap_duration_qualifying_cells": float(np.nanmean(duration_by_cell[qualifying_by_cell]))
                if qualifying_by_cell.any()
                else 0.0,
                "max_overlap_duration_days": float(np.nanmax(duration_by_cell)) if qualifying_by_cell.any() else 0.0,
                "max_cell_event_overlap_hwmid": float(np.nanmax(hwmid_by_cell)) if qualifying_by_cell.any() else 0.0,
            }
        ]
    )
    return event_summary, pd.DataFrame(daily_rows), pd.DataFrame(cell_rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_dir", type=Path)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--countries", nargs="+", default=["Germany", "France"])
    parser.add_argument("--reference-period", type=int, nargs=2, default=[1981, 2010])
    parser.add_argument("--event-start", type=pd.Timestamp, default=pd.Timestamp("2026-06-13"))
    parser.add_argument("--event-end", type=pd.Timestamp, default=pd.Timestamp("2026-06-29"))
    parser.add_argument("--include-years", type=int, nargs="*", default=[2019])
    parser.add_argument("--threshold-quantile", type=float, default=0.90)
    parser.add_argument("--min-heatwave-days", type=int, default=3)
    parser.add_argument("--top-years", type=int, default=20)
    parser.add_argument("--variable", default="t2m")
    parser.add_argument("--temperature-unit", default="K", choices=["K", "degC"])
    parser.add_argument("--allow-missing-boundary-years", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    main()
