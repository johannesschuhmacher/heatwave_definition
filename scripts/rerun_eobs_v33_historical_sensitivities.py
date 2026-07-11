"""Rebuild historical E-OBS v33.0e sensitivity tables for manuscript outputs."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import sys
import warnings

import netCDF4 as nc
import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from heatwave_definition.hwmid import _build_threshold_masks, _find_runs
from heatwave_definition.raw_eobs import filter_years_by_data_coverage, load_eobs_tx_country_cells
from heatwave_definition.regions import classify_countries_matrix
from scripts.sensitivity_country_sets import COUNTRY_SETS, WESTERN_CENTRAL_EUROPE
from scripts.sensitivity_country_weights import read_weight_sets
from scripts.sensitivity_ranking_criteria import CRITERIA


DEFAULT_OUTPUT_DIR = REPO / "outputs" / "eobs_current"
DEFAULT_SENSITIVITY_DIRS = [REPO / "outputs" / "sensitivity", REPO / "results" / "sensitivity"]
DEFAULT_TABLE_DIRS = [REPO / "outputs" / "appendix", REPO / "results" / "tables"]
DEFAULT_WEIGHTS = REPO / "outputs" / "sensitivity" / "country_weights_from_tyndp2024_pemmdb_nt2040.csv"


@dataclass(frozen=True)
class CellMetrics:
    years: np.ndarray
    hwmid: np.ndarray
    duration: np.ndarray
    annual_tmax: np.ndarray
    temp_anomaly: np.ndarray
    cell_lat: np.ndarray
    country_masks: dict[str, np.ndarray]


def main() -> None:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    metrics = build_metrics(args)
    np.savez_compressed(
        args.output_dir / "eobs_v33_wce_cell_metrics.npz",
        years=metrics.years,
        hwmid=metrics.hwmid,
        duration=metrics.duration,
        annual_tmax=metrics.annual_tmax,
        temp_anomaly=metrics.temp_anomaly,
        cell_lat=metrics.cell_lat,
        **{f"country_{country}": mask for country, mask in metrics.country_masks.items()},
    )

    country_top_years = country_set_rankings(metrics, args.top_years)
    country_top2 = country_top_years[country_top_years["rank"] <= 2].copy()
    write_replacing_historical(
        country_top_years,
        "country_set_top_years.csv",
        DEFAULT_SENSITIVITY_DIRS,
    )
    write_replacing_historical(
        country_top2,
        "country_set_top2_summary.csv",
        DEFAULT_SENSITIVITY_DIRS,
    )
    write_replacing_historical(country_top2, "country_mask_top2.csv", DEFAULT_TABLE_DIRS)

    criteria_top_years = ranking_criteria(metrics, args.top_years)
    criteria_top2 = criteria_top_years[criteria_top_years["rank"] <= 2].copy()
    write_replacing_historical(criteria_top_years, "ranking_criteria_top_years.csv", DEFAULT_SENSITIVITY_DIRS)
    write_replacing_historical(criteria_top2, "ranking_criteria_top2_summary.csv", DEFAULT_SENSITIVITY_DIRS)
    write_replacing_historical(criteria_top2, "ranking_criteria_top2.csv", DEFAULT_TABLE_DIRS)

    if args.weights.exists():
        weighted_top_years = country_weighted_rankings(metrics, args.weights, args.top_years)
        weighted_top2 = weighted_top_years[weighted_top_years["rank"] <= 2].copy()
        write_replacing_historical(weighted_top_years, "country_weighted_top_years.csv", DEFAULT_SENSITIVITY_DIRS)
        write_replacing_historical(weighted_top2, "country_weighted_top2_summary.csv", DEFAULT_SENSITIVITY_DIRS)
        write_replacing_historical(weighted_top2, "country_weighted_top2.csv", DEFAULT_TABLE_DIRS)

    print(args.output_dir / "eobs_v33_wce_cell_metrics.npz")
    print(country_top2.head(12).to_string(index=False))
    print(criteria_top2.head(12).to_string(index=False))


def build_metrics(args: argparse.Namespace) -> CellMetrics:
    daily_tmax, dates, cell_lat, _cell_lon, union_mask = load_eobs_tx_country_cells(
        [args.eobs],
        countries=WESTERN_CENTRAL_EUROPE,
        variable="tx",
        temperature_unit="degC",
    )
    daily_tmax, dates, _coverage = filter_years_by_data_coverage(
        daily_tmax,
        dates,
        min_valid_days_per_year=args.min_valid_days_per_year,
    )

    hwmid, duration, annual_tmax, temp_anomaly = calculate_cell_metrics(
        daily_tmax=daily_tmax,
        dates=dates,
        ref_period=tuple(args.reference_period),
        min_heatwave_days=args.min_heatwave_days,
        threshold_quantile=args.threshold_quantile,
    )

    with nc.Dataset(args.eobs, "r") as dataset:
        latitude = np.asarray(dataset.variables["latitude"][:], dtype=float)
        longitude = np.asarray(dataset.variables["longitude"][:], dtype=float)

    country_masks = {
        country: classify_countries_matrix(latitude, longitude, [country])[union_mask]
        for country in WESTERN_CENTRAL_EUROPE
    }
    years = np.array(sorted(pd.DatetimeIndex(dates).year.unique()), dtype=int)
    return CellMetrics(
        years=years,
        hwmid=hwmid,
        duration=duration,
        annual_tmax=annual_tmax,
        temp_anomaly=temp_anomaly,
        cell_lat=cell_lat.astype(float),
        country_masks=country_masks,
    )


def calculate_cell_metrics(
    daily_tmax: np.ndarray,
    dates: pd.DatetimeIndex,
    ref_period: tuple[int, int],
    min_heatwave_days: int,
    threshold_quantile: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    dates = pd.DatetimeIndex(dates)
    years = np.array(sorted(dates.year.unique()), dtype=int)
    year_to_pos = {year: idx for idx, year in enumerate(years)}
    year_masks = {year: dates.year == year for year in years}
    ref_years = list(range(int(ref_period[0]), int(ref_period[1]) + 1))
    ref_masks = {
        year: (dates >= pd.Timestamp(year, 1, 1)) & (dates <= pd.Timestamp(year, 12, 31))
        for year in ref_years
    }

    cell_count = daily_tmax.shape[1]
    thresholds = np.full((366, cell_count), np.nan, dtype=np.float32)
    threshold_masks = _build_threshold_masks(dates, ref_years)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=RuntimeWarning)
        for day, idx in enumerate(threshold_masks):
            if len(idx):
                thresholds[day, :] = np.nanquantile(daily_tmax[idx, :], threshold_quantile, axis=0)
        ref_annual_max = np.vstack([np.nanmax(daily_tmax[ref_masks[year], :], axis=0) for year in ref_years])
        annual_tmax = np.vstack([np.nanmax(daily_tmax[year_masks[year], :], axis=0) for year in years]).T

    temp_anomaly = annual_tmax - np.nanmean(ref_annual_max, axis=0)[:, None]
    denominator = np.nanquantile(ref_annual_max, 0.75, axis=0) - np.nanquantile(ref_annual_max, 0.25, axis=0)
    t25 = np.nanquantile(ref_annual_max, 0.25, axis=0)
    valid_cells = np.isfinite(denominator) & (denominator > 0)

    hwmid = np.zeros((cell_count, len(years)), dtype=np.float32)
    duration = np.zeros((cell_count, len(years)), dtype=np.float32)
    day_of_year = dates.dayofyear.to_numpy()
    for cell in range(cell_count):
        if not valid_cells[cell]:
            continue
        series = daily_tmax[:, cell].astype(float, copy=False)
        daily_thresholds = thresholds[day_of_year - 1, cell]
        above_threshold = np.isfinite(series) & (series > daily_thresholds)
        for start_idx, end_idx in _find_runs(above_threshold, min_heatwave_days):
            event_values = series[start_idx : end_idx + 1]
            daily_magnitude = np.maximum((event_values - t25[cell]) / denominator[cell], 0.0)
            magnitude = float(np.nansum(daily_magnitude))
            year_pos = year_to_pos.get(int(dates[start_idx].year))
            if year_pos is not None and magnitude > hwmid[cell, year_pos]:
                hwmid[cell, year_pos] = magnitude
                duration[cell, year_pos] = float(end_idx - start_idx + 1)

    return hwmid, duration, annual_tmax.astype(np.float32), temp_anomaly.astype(np.float32)


def country_set_rankings(metrics: CellMetrics, top_years: int) -> pd.DataFrame:
    rows = []
    for set_name, countries in COUNTRY_SETS.items():
        mask = countries_to_cell_mask(metrics, countries)
        scores = np.nansum(metrics.hwmid[mask, :], axis=0)
        ranking = ranked_rows(scores, metrics.years, top_years, "hwmid_sum")
        ranking.insert(0, "dataset", "Historical / E-OBS")
        ranking.insert(1, "country_set", set_name)
        ranking.insert(2, "countries", "+".join(countries))
        ranking["country_cells"] = int(mask.sum())
        ranking["aggregation"] = "sum"
        rows.append(ranking)
    return pd.concat(rows, ignore_index=True)


def ranking_criteria(metrics: CellMetrics, top_years: int) -> pd.DataFrame:
    rows = []
    mask = countries_to_cell_mask(metrics, ["Germany", "France"])
    area = np.cos(np.deg2rad(metrics.cell_lat[mask]))
    data_by_metric = {
        "hwmid": metrics.hwmid,
        "heatwave_duration": metrics.duration,
        "temp_anomaly": metrics.temp_anomaly,
    }
    for criterion in CRITERIA:
        values = data_by_metric.get(criterion.metric_name)
        if values is None:
            continue
        scores = aggregate(values[mask, :], area, criterion.aggregation)
        ranking = ranked_rows(scores, metrics.years, top_years, "score")
        ranking.insert(0, "dataset", "Historical / E-OBS")
        ranking.insert(1, "criterion", criterion.key)
        ranking.insert(2, "criterion_label", criterion.label)
        ranking.insert(3, "metric", criterion.metric_name)
        ranking["country_cells"] = int(mask.sum())
        ranking["aggregation"] = criterion.aggregation
        rows.append(ranking)
    return pd.concat(rows, ignore_index=True)


def country_weighted_rankings(metrics: CellMetrics, weights_path: Path, top_years: int) -> pd.DataFrame:
    rows = []
    area = np.cos(np.deg2rad(metrics.cell_lat))
    for weighting, country_weights in read_weight_sets(weights_path).items():
        cell_weights = np.zeros(metrics.hwmid.shape[0], dtype=float)
        for country, weight in country_weights.items():
            country_mask = metrics.country_masks.get(country)
            if country_mask is None or not country_mask.any() or weight <= 0:
                continue
            country_area = area[country_mask]
            country_cell_weights = country_area / np.nansum(country_area)
            cell_weights[country_mask] += float(weight) * country_cell_weights
        if np.nansum(cell_weights) <= 0:
            continue
        cell_weights = cell_weights / np.nansum(cell_weights)
        scores = np.nansum(metrics.hwmid * cell_weights[:, None], axis=0)
        ranking = ranked_rows(scores, metrics.years, top_years, "weighted_hwmid")
        ranking.insert(0, "dataset", "Historical / E-OBS")
        ranking.insert(1, "weighting", weighting)
        ranking["weighted_countries"] = "+".join(country_weights.keys())
        rows.append(ranking)
    return pd.concat(rows, ignore_index=True)


def countries_to_cell_mask(metrics: CellMetrics, countries: list[str]) -> np.ndarray:
    mask = np.zeros(metrics.hwmid.shape[0], dtype=bool)
    for country in countries:
        country_mask = metrics.country_masks.get(country)
        if country_mask is not None:
            mask |= country_mask
    if not mask.any():
        raise ValueError(f"Empty country mask for {countries!r}")
    return mask


def aggregate(values: np.ndarray, area: np.ndarray, aggregation: str) -> np.ndarray:
    if aggregation == "sum":
        return np.nansum(values, axis=0)
    if aggregation == "mean":
        return np.nanmean(values, axis=0)
    if aggregation == "max":
        return np.nanmax(values, axis=0)
    if aggregation == "area_weighted_mean":
        finite = np.isfinite(values)
        weighted = np.where(finite, values * area[:, None], 0.0)
        denominator = np.sum(np.where(finite, area[:, None], 0.0), axis=0)
        return np.divide(
            np.sum(weighted, axis=0),
            denominator,
            out=np.full(values.shape[1], np.nan, dtype=float),
            where=denominator > 0,
        )
    raise ValueError(f"Unsupported aggregation: {aggregation!r}")


def ranked_rows(scores: np.ndarray, years: np.ndarray, top_years: int, score_column: str) -> pd.DataFrame:
    order = np.argsort(scores)[::-1][:top_years]
    return pd.DataFrame(
        {
            "rank": np.arange(1, len(order) + 1),
            "year": years[order],
            score_column: scores[order],
        }
    )


def write_replacing_historical(new_rows: pd.DataFrame, filename: str, directories: list[Path]) -> None:
    for directory in directories:
        path = directory / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            old = pd.read_csv(path)
            old = old[old["dataset"] != "Historical / E-OBS"].copy()
            out = pd.concat([new_rows, old], ignore_index=True)
        else:
            out = new_rows.copy()
        out.to_csv(path, index=False)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("eobs", type=Path)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--weights", type=Path, default=DEFAULT_WEIGHTS)
    parser.add_argument("--reference-period", type=int, nargs=2, default=[1981, 2010])
    parser.add_argument("--threshold-quantile", type=float, default=0.90)
    parser.add_argument("--min-heatwave-days", type=int, default=3)
    parser.add_argument("--min-valid-days-per-year", type=int, default=300)
    parser.add_argument("--top-years", type=int, default=10)
    return parser.parse_args()


if __name__ == "__main__":
    main()
