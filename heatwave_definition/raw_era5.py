"""Memory-aware ranking from ERA5 hourly 2 m temperature NetCDF files."""

from __future__ import annotations

from pathlib import Path
import re

import netCDF4 as nc
import numpy as np
import pandas as pd

from .io import _decode_time, _first_existing_variable
from .raw_copernicus import _load_daily_tmax_for_mask, rank_daily_cells_by_hwmid
from .regions import classify_countries_matrix


def rank_era5_t2m_directory(
    directory: str | Path,
    countries: list[str],
    top_years: int = 10,
    ref_period: tuple[int, int] = (1981, 2010),
    min_heatwave_days: int = 3,
    threshold_quantile: float = 0.90,
    variable: str = "t2m",
    temperature_unit: str = "K",
    pattern: str = "t2m_era5_*.nc",
    start_year: int | None = None,
    end_year: int | None = None,
) -> pd.DataFrame:
    """Rank years by HWMId over country-mask cells from annual ERA5 files."""

    directory = Path(directory)
    files = sorted(directory.glob(pattern))
    files = filter_files_by_year(files, start_year=start_year, end_year=end_year)
    if not files:
        raise FileNotFoundError(f"No {pattern!r} files found in {directory}")

    daily_chunks = []
    date_chunks = []
    latitude = None
    longitude = None
    mask = None
    for path in files:
        with nc.Dataset(path, "r") as dataset:
            time_name = _first_existing_variable(dataset, ("valid_time", "time"))
            latitude_name = _first_existing_variable(dataset, ("latitude", "lat"))
            longitude_name = _first_existing_variable(dataset, ("longitude", "lon"))
            if variable not in dataset.variables:
                raise KeyError(f"Variable {variable!r} not found in {path}")

            dates_hourly = _decode_time(dataset.variables[time_name])
            day_index = dates_hourly.floor("D")
            daily_dates = pd.DatetimeIndex(pd.unique(day_index))
            file_latitude = np.asarray(dataset.variables[latitude_name][:])
            file_longitude = np.asarray(dataset.variables[longitude_name][:])

            if latitude is None:
                latitude = file_latitude
                longitude = file_longitude
                mask = classify_countries_matrix(latitude, longitude, countries)
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
    dates = pd.DatetimeIndex(dates.to_numpy()[order])
    daily_tmax = daily_tmax[order, :]

    ranking = rank_daily_cells_by_hwmid(
        daily_tmax=daily_tmax,
        dates=dates,
        top_years=top_years,
        ref_period=ref_period,
        min_heatwave_days=min_heatwave_days,
        threshold_quantile=threshold_quantile,
    )
    ranking["country_cells"] = int(mask.sum()) if mask is not None else 0
    ranking["countries"] = "+".join(countries)
    ranking["source_file_count"] = len(files)
    ranking["source_directory_name"] = directory.name
    ranking["source_year_start"] = min(_year_from_filename(path) for path in files)
    ranking["source_year_end"] = max(_year_from_filename(path) for path in files)
    return ranking


def era5_year_coverage(
    directory: str | Path,
    pattern: str = "t2m_era5_*.nc",
    start_year: int | None = None,
    end_year: int | None = None,
) -> pd.DataFrame:
    """Report available hourly and daily coverage for annual ERA5 files."""

    directory = Path(directory)
    files = sorted(directory.glob(pattern))
    files = filter_files_by_year(files, start_year=start_year, end_year=end_year)
    rows = []
    for path in files:
        with nc.Dataset(path, "r") as dataset:
            time_name = _first_existing_variable(dataset, ("valid_time", "time"))
            dates_hourly = _decode_time(dataset.variables[time_name])
            daily_dates = pd.DatetimeIndex(pd.unique(dates_hourly.floor("D")))
        rows.append(
            {
                "year": _year_from_filename(path),
                "file_name": path.name,
                "first_timestamp": dates_hourly.min().isoformat(),
                "last_timestamp": dates_hourly.max().isoformat(),
                "hourly_steps": int(len(dates_hourly)),
                "daily_steps": int(len(daily_dates)),
                "complete_year": bool(len(daily_dates) >= expected_days_in_year(int(_year_from_filename(path)))),
                "size_bytes": path.stat().st_size,
            }
        )
    return pd.DataFrame(rows)


def filter_files_by_year(files: list[Path], start_year: int | None, end_year: int | None) -> list[Path]:
    if start_year is None and end_year is None:
        return files
    filtered = []
    for path in files:
        year = _year_from_filename(path)
        if year is None:
            continue
        if start_year is not None and year < start_year:
            continue
        if end_year is not None and year > end_year:
            continue
        filtered.append(path)
    return filtered


def _year_from_filename(path: Path) -> int | None:
    match = re.search(r"(\d{4})(?=\.nc$)", path.name)
    return int(match.group(1)) if match else None


def expected_days_in_year(year: int) -> int:
    return 366 if pd.Timestamp(year, 12, 31).is_leap_year else 365
