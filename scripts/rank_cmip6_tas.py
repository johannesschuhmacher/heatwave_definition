"""Rank CORDEX-CMIP6/ICON-CLM tas files by Germany-France HWMId.

The CMIP6 data on LSDF are split into historical and SSP annual files. For SSP
runs this script loads the matching historical segment as the HWMId reference
period and ranks only the future scenario years.
"""

from __future__ import annotations

import argparse
import gc
import hashlib
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path

import netCDF4 as nc
import numpy as np
import pandas as pd

from heatwave_definition.io import _decode_time
from heatwave_definition.hwmid import HWMID_METHOD_ID
from heatwave_definition.raw_copernicus import _load_daily_tmax_for_mask, rank_daily_cells_by_hwmid
from heatwave_definition.regions import classify_countries_matrix


REPO = Path(__file__).resolve().parents[1]
DEFAULT_ROOT = Path(os.environ.get("HEATWAVE_CMIP6_ROOT", "data/cordex_cmip6/netcdf"))
DEFAULT_OUTPUT = REPO / "outputs" / "climate_data" / "cmip6_de_fr_top_years.csv"
DEFAULT_INVENTORY = REPO / "outputs" / "climate_data" / "cmip6_de_fr_run_inventory.csv"
DEFAULT_FILE_INVENTORY = REPO / "outputs" / "climate_data" / "cmip6_de_fr_file_inventory.csv"
DEFAULT_CACHE_DIR = REPO / "outputs" / "climate_data" / "daily_cache"


@dataclass(frozen=True)
class Cmip6Group:
    institution: str
    rcm: str
    gcm: str
    scenario: str
    variant: str
    version: str
    frequency: str
    variable: str
    files: tuple[Path, ...]

    @property
    def chain_key(self) -> tuple[str, str, str, str, str, str]:
        return (self.institution, self.rcm, self.gcm, self.variant, self.version, self.frequency)

    @property
    def label(self) -> str:
        return f"CORDEX-CMIP6 {self.gcm} / {self.rcm} {self.scenario.upper()}"


@dataclass
class DailySubset:
    dates: pd.DatetimeIndex
    daily_tmax: np.ndarray
    mask: np.ndarray
    latitude: np.ndarray
    longitude: np.ndarray


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.inventory.parent.mkdir(parents=True, exist_ok=True)
    args.file_inventory.parent.mkdir(parents=True, exist_ok=True)
    if args.cache_dir is not None:
        args.cache_dir.mkdir(parents=True, exist_ok=True)

    groups = discover_cmip6_tas_groups(args.root, variable=args.variable, frequency=args.frequency)
    groups = filter_groups(groups, scenarios=args.scenarios, gcms=args.gcms)
    historical_by_chain = {group.chain_key: group for group in groups if group.scenario == "historical"}
    eligible_chain_keys = {
        key
        for key, historical in historical_by_chain.items()
        if not missing_reference_years(historical, tuple(args.reference_period))
    }
    inventory = inventory_table(groups, historical_by_chain, tuple(args.reference_period))
    inventory.to_csv(args.inventory, index=False)
    print(args.inventory)
    file_inventory_table(groups, args.root).to_csv(args.file_inventory, index=False)
    print(args.file_inventory)

    future_groups = [group for group in groups if group.scenario != "historical"]

    run_order = []
    for key, historical in historical_by_chain.items():
        if key not in eligible_chain_keys:
            missing = missing_reference_years(historical, tuple(args.reference_period))
            print(
                f"Skipping {historical.gcm} {historical.variant}: historical reference "
                f"is missing years {format_year_ranges(missing)}"
            )
            continue
        run_order.append(historical)
        run_order.extend(group for group in future_groups if group.chain_key == historical.chain_key)
    if args.max_runs is not None:
        run_order = run_order[: args.max_runs]

    all_rankings: list[pd.DataFrame] = []
    if args.output.exists() and args.resume:
        existing = pd.read_csv(args.output)
        completed, stale = classify_resume_groups(
            existing,
            run_order,
            historical_by_chain,
            tuple(args.reference_period),
        )
        existing = enrich_resumed_rows(
            existing[~existing["dataset"].isin(stale)].copy(),
            run_order,
            historical_by_chain,
            tuple(args.reference_period),
        )
        if not existing.empty:
            all_rankings.append(existing)
    else:
        completed = set()

    loaded_historical: dict[tuple[str, str, str, str, str, str], DailySubset] = {}
    loaded_historical_file_counts: dict[tuple[str, str, str, str, str, str], int] = {}
    for idx, group in enumerate(run_order, start=1):
        if group.label in completed:
            print(f"[{idx}/{len(run_order)}] skip existing {group.label}")
            continue

        group_started = time.perf_counter()
        print(f"[{idx}/{len(run_order)}] {group.label} ({len(group.files)} scenario files)", flush=True)
        historical = historical_by_chain.get(group.chain_key)
        if historical is None:
            print(f"  skipped: no matching historical reference for {group.gcm} {group.variant}")
            continue

        hist_subset = loaded_historical.get(group.chain_key)
        if hist_subset is None:
            historical_files = historical.files
            if group.scenario != "historical":
                ref_start, ref_end = tuple(args.reference_period)
                historical_files = files_for_year_range(historical.files, ref_start - 1, ref_end + 1)
            print(f"  loading historical reference: {historical.label} ({len(historical_files)} files)")
            hist_subset = load_daily_subset(
                historical_files,
                countries=args.countries,
                variable=args.variable,
                temperature_unit=args.temperature_unit,
                cache_dir=args.cache_dir,
            )
            loaded_historical[group.chain_key] = hist_subset
            loaded_historical_file_counts[group.chain_key] = len(historical_files)

        if group.scenario == "historical":
            dates = hist_subset.dates
            daily_tmax = hist_subset.daily_tmax
            rank_start = args.historical_rank_start
            rank_end = args.historical_rank_end
            source_file_count = len(historical.files)
        else:
            scenario_subset = load_daily_subset(
                group.files,
                countries=args.countries,
                variable=args.variable,
                temperature_unit=args.temperature_unit,
                mask=hist_subset.mask,
                latitude=hist_subset.latitude,
                longitude=hist_subset.longitude,
                cache_dir=args.cache_dir,
            )
            dates = pd.DatetimeIndex(np.concatenate([hist_subset.dates.to_numpy(), scenario_subset.dates.to_numpy()]))
            daily_tmax = np.vstack([hist_subset.daily_tmax, scenario_subset.daily_tmax])
            order = np.argsort(dates.to_numpy())
            dates = pd.DatetimeIndex(dates.to_numpy()[order])
            daily_tmax = daily_tmax[order, :]
            rank_start = args.future_rank_start
            rank_end = args.future_rank_end
            source_file_count = loaded_historical_file_counts[group.chain_key] + len(group.files)

        ranking = rank_daily_cells_by_hwmid(
            daily_tmax=daily_tmax,
            dates=dates,
            top_years=args.top_years,
            ref_period=tuple(args.reference_period),
            min_heatwave_days=args.min_heatwave_days,
            threshold_quantile=args.threshold_quantile,
            rank_year_start=rank_start,
            rank_year_end=rank_end,
        )
        ranking.insert(0, "dataset", group.label)
        ranking.insert(1, "data_family", "CORDEX-CMIP6")
        ranking.insert(2, "scenario", group.scenario.upper())
        ranking.insert(3, "gcm", group.gcm)
        ranking.insert(4, "rcm", group.rcm)
        ranking.insert(5, "variant", group.variant)
        ranking["country_cells"] = int(hist_subset.mask.sum())
        ranking["countries"] = "+".join(args.countries)
        ranking["source_file_count"] = source_file_count
        reference_files = reference_files_for_group(group, historical, tuple(args.reference_period))
        ranking["scenario_file_count"] = len(group.files)
        ranking["reference_file_count"] = len(reference_files)
        ranking["source_inventory_name_size_sha256"] = source_inventory_signature(
            group.files + reference_files
        )
        ranking["available_year_start"] = int(dates.year.min())
        ranking["available_year_end"] = int(dates.year.max())
        ranking["rank_year_start"] = rank_start
        ranking["rank_year_end"] = rank_end
        all_rankings.append(ranking)
        pd.concat(all_rankings, ignore_index=True).to_csv(args.output, index=False)
        print(ranking.head(args.top_years).to_string(index=False))
        print(f"  wrote partial results: {args.output}")
        print(f"  completed in {(time.perf_counter() - group_started) / 60:.1f} min", flush=True)

        if group.scenario != "historical":
            del scenario_subset, dates, daily_tmax
            gc.collect()

    if not all_rankings:
        raise SystemExit("No CMIP6 rankings were generated")

    result = pd.concat(all_rankings, ignore_index=True)
    result.to_csv(args.output, index=False)
    print(args.output)


def classify_resume_groups(
    existing: pd.DataFrame,
    run_order: list[Cmip6Group],
    historical_by_chain: dict[tuple[str, str, str, str, str, str], Cmip6Group],
    reference_period: tuple[int, int],
) -> tuple[set[str], set[str]]:
    completed: set[str] = set()
    stale: set[str] = set()
    for group in run_order:
        rows = existing[existing["dataset"] == group.label]
        if rows.empty:
            stale.add(group.label)
            continue
        expected_end = max(year_from_filename(path) for path in group.files)
        recorded_end = int(pd.to_numeric(rows["available_year_end"], errors="coerce").max())
        file_count_matches = True
        if "scenario_file_count" in rows:
            recorded_count = int(pd.to_numeric(rows["scenario_file_count"], errors="coerce").max())
            file_count_matches = recorded_count == len(group.files)
        method_matches = (
            "hwmid_method" in rows
            and set(rows["hwmid_method"].dropna().astype(str)) == {HWMID_METHOD_ID}
        )
        if recorded_end == expected_end and file_count_matches and method_matches:
            completed.add(group.label)
        else:
            stale.add(group.label)
    return completed, stale


def enrich_resumed_rows(
    existing: pd.DataFrame,
    run_order: list[Cmip6Group],
    historical_by_chain: dict[tuple[str, str, str, str, str, str], Cmip6Group],
    reference_period: tuple[int, int],
) -> pd.DataFrame:
    for group in run_order:
        mask = existing["dataset"] == group.label
        if not mask.any():
            continue
        historical = historical_by_chain[group.chain_key]
        reference_files = reference_files_for_group(group, historical, reference_period)
        existing.loc[mask, "scenario_file_count"] = len(group.files)
        existing.loc[mask, "reference_file_count"] = len(reference_files)
        existing.loc[mask, "source_inventory_name_size_sha256"] = source_inventory_signature(
            group.files + reference_files
        )
    return existing


def reference_files_for_group(
    group: Cmip6Group,
    historical: Cmip6Group,
    reference_period: tuple[int, int],
) -> tuple[Path, ...]:
    if group.scenario == "historical":
        return ()
    ref_start, ref_end = reference_period
    return files_for_year_range(historical.files, ref_start - 1, ref_end + 1)


def source_inventory_signature(files: tuple[Path, ...]) -> str:
    """Hash sorted source file names and byte sizes, not file contents."""

    digest = hashlib.sha256()
    for path in sorted(files):
        stat = path.stat()
        digest.update(path.name.encode("utf-8"))
        digest.update(str(stat.st_size).encode("ascii"))
    return digest.hexdigest()


def discover_cmip6_tas_groups(root: Path, variable: str, frequency: str) -> list[Cmip6Group]:
    files = sorted(root.rglob(f"{variable}_*.nc"))
    grouped: dict[tuple[str, str, str, str, str, str, str, str], list[Path]] = {}
    for path in files:
        parsed = parse_cmip6_path(root, path)
        if parsed is None:
            continue
        key = parsed[:-1]
        if key[-2] != frequency or key[-1] != variable:
            continue
        grouped.setdefault(key, []).append(path)

    groups = []
    for key, paths in sorted(grouped.items()):
        institution, rcm, gcm, scenario, variant, version, freq, var = key
        groups.append(
            Cmip6Group(
                institution=institution,
                rcm=rcm,
                gcm=gcm,
                scenario=scenario,
                variant=variant,
                version=version,
                frequency=freq,
                variable=var,
                files=tuple(sorted(paths, key=year_from_filename)),
            )
        )
    return groups


def parse_cmip6_path(root: Path, path: Path) -> tuple[str, str, str, str, str, str, str, str, Path] | None:
    try:
        rel = path.relative_to(root)
    except ValueError:
        return None
    parts = rel.parts
    if len(parts) < 10:
        return None
    domain, institution, rcm, gcm, scenario, variant, version, frequency, variable = parts[:9]
    if domain != "EUR-12":
        return None
    return institution, rcm, gcm, scenario, variant, version, frequency, variable, path


def filter_groups(groups: list[Cmip6Group], scenarios: list[str] | None, gcms: list[str] | None) -> list[Cmip6Group]:
    if scenarios:
        wanted = {scenario.lower() for scenario in scenarios}
        groups = [group for group in groups if group.scenario.lower() in wanted or group.scenario == "historical"]
    if gcms:
        wanted_gcms = {gcm.lower() for gcm in gcms}
        groups = [group for group in groups if group.gcm.lower() in wanted_gcms]
    return groups


def load_daily_subset(
    files: tuple[Path, ...],
    countries: list[str],
    variable: str,
    temperature_unit: str,
    mask: np.ndarray | None = None,
    latitude: np.ndarray | None = None,
    longitude: np.ndarray | None = None,
    cache_dir: Path | None = None,
) -> DailySubset:
    daily_chunks = []
    date_chunks = []
    working_mask = mask
    working_latitude = latitude
    working_longitude = longitude

    for file_idx, path in enumerate(files, start=1):
        file_started = time.perf_counter()
        print(f"    [{file_idx}/{len(files)}] {path.name}", flush=True)
        cache_path = daily_cache_path(path, cache_dir, countries, variable, temperature_unit) if cache_dir else None
        if cache_path is not None and cache_path.exists():
            with np.load(cache_path, allow_pickle=False) as cached:
                cached_dates = pd.DatetimeIndex(cached["dates"].astype("datetime64[ns]"))
                cached_daily = cached["daily_tmax"].astype(np.float32, copy=False)
            if working_mask is None:
                with nc.Dataset(path, "r") as dataset:
                    working_latitude = np.asarray(dataset.variables["lat"][:])
                    working_longitude = np.asarray(dataset.variables["lon"][:])
                    working_mask = classify_countries_matrix(working_latitude, working_longitude, countries)
            expected_cells = int(working_mask.sum())
            if cached_daily.shape[1] != expected_cells:
                raise ValueError(
                    f"Cache cell count mismatch for {path.name}: "
                    f"{cached_daily.shape[1]} cached, {expected_cells} expected"
                )
            daily_chunks.append(cached_daily)
            date_chunks.append(cached_dates)
            print(f"      loaded cache in {time.perf_counter() - file_started:.1f} s", flush=True)
            continue

        with nc.Dataset(path, "r") as dataset:
            dates_hourly = _decode_time(dataset.variables["time"])
            day_index = dates_hourly.floor("D")
            daily_dates = pd.DatetimeIndex(pd.unique(day_index))
            file_latitude = np.asarray(dataset.variables["lat"][:])
            file_longitude = np.asarray(dataset.variables["lon"][:])

            if working_latitude is None:
                working_latitude = file_latitude
                working_longitude = file_longitude
                working_mask = classify_countries_matrix(file_latitude, file_longitude, countries)
            elif not (
                np.array_equal(working_latitude, file_latitude)
                and np.array_equal(working_longitude, file_longitude)
            ):
                raise ValueError(f"Grid coordinates changed in {path}")

            daily_tmax = _load_daily_tmax_for_mask(
                dataset.variables[variable],
                dates_hourly,
                day_index,
                daily_dates,
                working_mask,
                temperature_unit=temperature_unit,
            )
            daily_chunks.append(daily_tmax)
            date_chunks.append(daily_dates)
            if cache_path is not None:
                np.savez(
                    cache_path,
                    dates=daily_dates.to_numpy(dtype="datetime64[ns]"),
                    daily_tmax=daily_tmax,
                )
        print(f"      loaded in {time.perf_counter() - file_started:.1f} s", flush=True)

    dates = pd.DatetimeIndex(np.concatenate([chunk.to_numpy() for chunk in date_chunks]))
    daily_tmax = np.vstack(daily_chunks)
    order = np.argsort(dates.to_numpy())
    dates = pd.DatetimeIndex(dates.to_numpy()[order])
    daily_tmax = daily_tmax[order, :]
    if working_mask is None or working_latitude is None or working_longitude is None:
        raise ValueError("No CMIP6 files were loaded")
    return DailySubset(dates=dates, daily_tmax=daily_tmax, mask=working_mask, latitude=working_latitude, longitude=working_longitude)


def daily_cache_path(
    path: Path,
    cache_dir: Path,
    countries: list[str],
    variable: str,
    temperature_unit: str,
) -> Path:
    country_key = "-".join(country.lower().replace(" ", "_") for country in countries)
    digest = hashlib.sha1(str(path).lower().encode("utf-8")).hexdigest()[:12]
    return cache_dir / f"{path.stem}_{country_key}_{variable}_{temperature_unit}_{digest}.npz"


def inventory_table(
    groups: list[Cmip6Group],
    historical_by_chain: dict[tuple[str, str, str, str, str, str], Cmip6Group],
    reference_period: tuple[int, int],
) -> pd.DataFrame:
    rows = []
    for group in groups:
        years = [year_from_filename(path) for path in group.files]
        historical = historical_by_chain.get(group.chain_key)
        missing = (
            missing_reference_years(historical, reference_period)
            if historical is not None
            else list(range(reference_period[0] - 1, reference_period[1] + 2))
        )
        rows.append(
            {
                "dataset": group.label,
                "institution": group.institution,
                "rcm": group.rcm,
                "gcm": group.gcm,
                "scenario": group.scenario.upper(),
                "variant": group.variant,
                "version": group.version,
                "frequency": group.frequency,
                "variable": group.variable,
                "file_count": len(group.files),
                "year_start": min(years),
                "year_end": max(years),
                "size_gb": sum(path.stat().st_size for path in group.files) / 1e9,
                "eligible_for_ranking": not missing,
                "missing_reference_years": format_year_ranges(missing),
            }
        )
    return pd.DataFrame.from_records(rows)


def missing_reference_years(
    historical: Cmip6Group,
    reference_period: tuple[int, int],
) -> list[int]:
    """Return missing historical years, including threshold-window boundaries."""

    available = {year_from_filename(path) for path in historical.files}
    required = set(range(reference_period[0] - 1, reference_period[1] + 2))
    return sorted(required - available)


def format_year_ranges(years: list[int]) -> str:
    """Format integer years as compact comma-separated ranges."""

    if not years:
        return ""
    ranges: list[str] = []
    start = previous = years[0]
    for year in years[1:]:
        if year == previous + 1:
            previous = year
            continue
        ranges.append(str(start) if start == previous else f"{start}-{previous}")
        start = previous = year
    ranges.append(str(start) if start == previous else f"{start}-{previous}")
    return ",".join(ranges)


def file_inventory_table(groups: list[Cmip6Group], root: Path) -> pd.DataFrame:
    rows = []
    for group in groups:
        for path in group.files:
            relative_path = path.relative_to(root).as_posix()
            size_bytes = path.stat().st_size
            rows.append(
                {
                    "dataset": group.label,
                    "scenario": group.scenario.upper(),
                    "gcm": group.gcm,
                    "rcm": group.rcm,
                    "variant": group.variant,
                    "version": group.version,
                    "frequency": group.frequency,
                    "variable": group.variable,
                    "year": year_from_filename(path),
                    "relative_path": relative_path,
                    "file_name": path.name,
                    "size_bytes": size_bytes,
                    "name_size_sha256": hashlib.sha256(
                        f"{relative_path}\t{size_bytes}".encode("utf-8")
                    ).hexdigest(),
                }
            )
    return pd.DataFrame.from_records(rows)


def files_for_year_range(files: tuple[Path, ...], year_start: int, year_end: int) -> tuple[Path, ...]:
    filtered = tuple(path for path in files if year_start <= year_from_filename(path) <= year_end)
    if not filtered:
        raise ValueError(f"No files found for {year_start}-{year_end}")
    return filtered


def year_from_filename(path: Path) -> int:
    match = re.search(r"_(\d{4})\d{10,}-\d{4}\d{10,}\.nc$", path.name)
    if match:
        return int(match.group(1))
    match = re.search(r"_(\d{4})", path.name)
    if match:
        return int(match.group(1))
    raise ValueError(f"Cannot parse year from {path.name}")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--inventory", type=Path, default=DEFAULT_INVENTORY)
    parser.add_argument("--file-inventory", type=Path, default=DEFAULT_FILE_INVENTORY)
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE_DIR)
    parser.add_argument("--countries", nargs="+", default=["Germany", "France"])
    parser.add_argument("--variable", default="tas")
    parser.add_argument("--frequency", default="1hrPt")
    parser.add_argument("--temperature-unit", default="K", choices=["K", "degC"])
    parser.add_argument("--reference-period", nargs=2, type=int, default=[1981, 2010])
    parser.add_argument("--threshold-quantile", type=float, default=0.90)
    parser.add_argument("--min-heatwave-days", type=int, default=3)
    parser.add_argument("--top-years", type=int, default=10)
    parser.add_argument("--historical-rank-start", type=int, default=1950)
    parser.add_argument("--historical-rank-end", type=int, default=2014)
    parser.add_argument("--future-rank-start", type=int, default=2015)
    parser.add_argument("--future-rank-end", type=int)
    parser.add_argument("--scenarios", nargs="*", help="Optional future scenario filters, e.g. ssp126 ssp245 ssp370.")
    parser.add_argument("--gcms", nargs="*", help="Optional GCM filters, e.g. CNRM-ESM2-1 MPI-ESM1-2-HR.")
    parser.add_argument("--max-runs", type=int, help="Process only the first N grouped runs.")
    parser.add_argument("--resume", action="store_true", help="Skip datasets already present in the output CSV.")
    return parser.parse_args(argv)


if __name__ == "__main__":
    main()
