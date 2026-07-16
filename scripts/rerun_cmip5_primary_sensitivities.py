"""Rebuild primary CMIP5 sensitivity tables from raw tasAdjust files."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import sys

import netCDF4 as nc
import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from heatwave_definition.io import _decode_time
from heatwave_definition.hwmid import HWMID_METHOD_ID
from heatwave_definition.raw_copernicus import (
    _load_daily_tmax_for_mask,
    discover_tasadjust_runs,
)
from heatwave_definition.regions import classify_countries_matrix
from scripts.rerun_eobs_v33_historical_sensitivities import (
    aggregate,
    calculate_cell_metrics,
    ranked_rows,
)
from scripts.sensitivity_country_sets import COUNTRY_SETS, WESTERN_CENTRAL_EUROPE
from scripts.sensitivity_country_weights import read_weight_sets
from scripts.sensitivity_ranking_criteria import CRITERIA


DEFAULT_OUTPUT_DIR = REPO / "outputs" / "cmip5_current"
DEFAULT_SENSITIVITY_DIRS = [REPO / "outputs" / "sensitivity", REPO / "results" / "sensitivity"]
DEFAULT_TABLE_DIRS = [REPO / "outputs" / "appendix", REPO / "results" / "tables"]
DEFAULT_WEIGHTS = REPO / "outputs" / "sensitivity" / "country_weights_from_tyndp2024_pemmdb_nt2040.csv"

PRIMARY_RUNS = [
    {
        "dataset": "RCP4.5 / IPSL-WRF",
        "scenario": "RCP45",
        "driving_model": "IPSL-IPSL-CM5A-MR",
        "regional_model": "IPSL-WRF381P",
        "slug": "rcp45_ipsl_wrf",
    },
    {
        "dataset": "RCP8.5 / MPI-CLM",
        "scenario": "RCP85",
        "driving_model": "MPI-M-MPI-ESM-LR",
        "regional_model": "CLMcom-CCLM4-8-17",
        "slug": "rcp85_mpi_clm",
    },
]


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
    runs = discover_tasadjust_runs(args.root)

    all_manifest_rows = []
    for spec in PRIMARY_RUNS:
        run = select_run(runs, spec)
        print(f"Processing {spec['dataset']}: {run.path}")
        metrics = build_metrics(
            run.path,
            reference_period=tuple(args.reference_period),
            threshold_quantile=args.threshold_quantile,
            min_heatwave_days=args.min_heatwave_days,
        )
        metric_path = args.output_dir / f"cmip5_{spec['slug']}_wce_cell_metrics.npz"
        np.savez_compressed(
            metric_path,
            years=metrics.years,
            hwmid_method=np.asarray(HWMID_METHOD_ID),
            hwmid=metrics.hwmid,
            duration=metrics.duration,
            annual_tmax=metrics.annual_tmax,
            temp_anomaly=metrics.temp_anomaly,
            cell_lat=metrics.cell_lat,
            **{f"country_{country}": mask for country, mask in metrics.country_masks.items()},
        )
        all_manifest_rows.append(
            {
                "dataset": spec["dataset"],
                "source_file_name": run.path.name,
                "metrics_file_name": metric_path.name,
                "year_start": int(metrics.years.min()),
                "year_end": int(metrics.years.max()),
                "cell_count": int(metrics.hwmid.shape[0]),
            }
        )

        country_top_years = country_set_rankings(metrics, spec["dataset"], args.top_years)
        criteria_top_years = ranking_criteria(metrics, spec["dataset"], args.top_years)
        weighted_top_years = country_weighted_rankings(metrics, spec["dataset"], args.weights, args.top_years)

        write_replacing_dataset(country_top_years, "country_set_top_years.csv", DEFAULT_SENSITIVITY_DIRS, spec["dataset"])
        write_replacing_dataset(
            country_top_years[country_top_years["rank"] <= 2],
            "country_set_top2_summary.csv",
            DEFAULT_SENSITIVITY_DIRS,
            spec["dataset"],
        )
        write_replacing_dataset(
            country_top_years[country_top_years["rank"] <= 2],
            "country_mask_top2.csv",
            DEFAULT_TABLE_DIRS,
            spec["dataset"],
        )

        write_replacing_dataset(criteria_top_years, "ranking_criteria_top_years.csv", DEFAULT_SENSITIVITY_DIRS, spec["dataset"])
        write_replacing_dataset(
            criteria_top_years[criteria_top_years["rank"] <= 2],
            "ranking_criteria_top2_summary.csv",
            DEFAULT_SENSITIVITY_DIRS,
            spec["dataset"],
        )
        write_replacing_dataset(
            criteria_top_years[criteria_top_years["rank"] <= 2],
            "ranking_criteria_top2.csv",
            DEFAULT_TABLE_DIRS,
            spec["dataset"],
        )

        write_replacing_dataset(weighted_top_years, "country_weighted_top_years.csv", DEFAULT_SENSITIVITY_DIRS, spec["dataset"])
        write_replacing_dataset(
            weighted_top_years[weighted_top_years["rank"] <= 2],
            "country_weighted_top2_summary.csv",
            DEFAULT_SENSITIVITY_DIRS,
            spec["dataset"],
        )
        write_replacing_dataset(
            weighted_top_years[weighted_top_years["rank"] <= 2],
            "country_weighted_top2.csv",
            DEFAULT_TABLE_DIRS,
            spec["dataset"],
        )

    manifest = pd.DataFrame(all_manifest_rows)
    manifest_path = args.output_dir / "cmip5_primary_sensitivity_manifest.csv"
    manifest.to_csv(manifest_path, index=False)
    print(manifest_path)
    print(manifest.to_string(index=False))


def select_run(runs, spec: dict[str, str]):
    matches = [
        run
        for run in runs
        if run.scenario == spec["scenario"]
        and run.driving_model == spec["driving_model"]
        and run.regional_model == spec["regional_model"]
    ]
    if len(matches) != 1:
        raise ValueError(f"Expected exactly one raw run for {spec['dataset']}, found {len(matches)}")
    return matches[0]


def build_metrics(
    path: Path,
    reference_period: tuple[int, int],
    threshold_quantile: float,
    min_heatwave_days: int,
) -> CellMetrics:
    with nc.Dataset(path, "r") as dataset:
        dates_3h = _decode_time(dataset.variables["time"])
        day_index = dates_3h.floor("D")
        daily_dates = pd.DatetimeIndex(pd.unique(day_index))
        latitude = np.asarray(dataset.variables["lat"][:], dtype=float)
        longitude = np.asarray(dataset.variables["lon"][:], dtype=float)
        union_mask = classify_countries_matrix(latitude, longitude, WESTERN_CENTRAL_EUROPE)
        lon_grid, lat_grid = np.meshgrid(longitude, latitude)
        cell_lat = lat_grid[union_mask]
        daily_tmax = _load_daily_tmax_for_mask(
            dataset.variables["tasAdjust"],
            dates_3h,
            day_index,
            daily_dates,
            union_mask,
            temperature_unit="K",
        )

    hwmid, duration, annual_tmax, temp_anomaly = calculate_cell_metrics(
        daily_tmax=daily_tmax,
        dates=daily_dates,
        ref_period=reference_period,
        min_heatwave_days=min_heatwave_days,
        threshold_quantile=threshold_quantile,
    )
    country_masks = {
        country: classify_countries_matrix(latitude, longitude, [country])[union_mask]
        for country in WESTERN_CENTRAL_EUROPE
    }
    years = np.array(sorted(daily_dates.year.unique()), dtype=int)
    return CellMetrics(
        years=years,
        hwmid=hwmid,
        duration=duration,
        annual_tmax=annual_tmax,
        temp_anomaly=temp_anomaly,
        cell_lat=cell_lat.astype(float),
        country_masks=country_masks,
    )


def country_set_rankings(metrics: CellMetrics, dataset: str, top_years: int) -> pd.DataFrame:
    rows = []
    for set_name, countries in COUNTRY_SETS.items():
        mask = countries_to_cell_mask(metrics, countries)
        scores = np.nansum(metrics.hwmid[mask, :], axis=0)
        ranking = ranked_rows(scores, metrics.years, top_years, "hwmid_sum")
        ranking.insert(0, "dataset", dataset)
        ranking.insert(1, "country_set", set_name)
        ranking.insert(2, "countries", "+".join(countries))
        ranking["country_cells"] = int(mask.sum())
        ranking["aggregation"] = "sum"
        rows.append(ranking)
    return pd.concat(rows, ignore_index=True)


def ranking_criteria(metrics: CellMetrics, dataset: str, top_years: int) -> pd.DataFrame:
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
        ranking.insert(0, "dataset", dataset)
        ranking.insert(1, "criterion", criterion.key)
        ranking.insert(2, "criterion_label", criterion.label)
        ranking.insert(3, "metric", criterion.metric_name)
        ranking["country_cells"] = int(mask.sum())
        ranking["aggregation"] = criterion.aggregation
        rows.append(ranking)
    return pd.concat(rows, ignore_index=True)


def country_weighted_rankings(metrics: CellMetrics, dataset: str, weights_path: Path, top_years: int) -> pd.DataFrame:
    rows = []
    area = np.cos(np.deg2rad(metrics.cell_lat))
    for weighting, country_weights in read_weight_sets(weights_path).items():
        cell_weights = np.zeros(metrics.hwmid.shape[0], dtype=float)
        for country, weight in country_weights.items():
            country_mask = metrics.country_masks.get(country)
            if country_mask is None or not country_mask.any() or weight <= 0:
                continue
            country_area = area[country_mask]
            cell_weights[country_mask] += float(weight) * country_area / np.nansum(country_area)
        if np.nansum(cell_weights) <= 0:
            continue
        cell_weights = cell_weights / np.nansum(cell_weights)
        scores = np.nansum(metrics.hwmid * cell_weights[:, None], axis=0)
        ranking = ranked_rows(scores, metrics.years, top_years, "weighted_hwmid")
        ranking.insert(0, "dataset", dataset)
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


def write_replacing_dataset(new_rows: pd.DataFrame, filename: str, directories: list[Path], dataset: str) -> None:
    new_rows = new_rows.copy()
    new_rows["hwmid_method"] = HWMID_METHOD_ID
    for directory in directories:
        path = directory / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            old = pd.read_csv(path)
            old = old[old["dataset"] != dataset].copy()
            out = pd.concat([old, new_rows], ignore_index=True)
        else:
            out = new_rows.copy()
        out.to_csv(path, index=False)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--weights", type=Path, default=DEFAULT_WEIGHTS)
    parser.add_argument("--reference-period", type=int, nargs=2, default=[1981, 2010])
    parser.add_argument("--threshold-quantile", type=float, default=0.90)
    parser.add_argument("--min-heatwave-days", type=int, default=3)
    parser.add_argument("--top-years", type=int, default=10)
    return parser.parse_args()


if __name__ == "__main__":
    main()
