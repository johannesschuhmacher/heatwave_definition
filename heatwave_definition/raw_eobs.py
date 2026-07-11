"""Memory-aware ranking from E-OBS daily maximum-temperature files."""

from __future__ import annotations

from pathlib import Path

import netCDF4 as nc
import numpy as np
import pandas as pd

from .io import _decode_time, _first_existing_variable
from .raw_copernicus import rank_daily_cells_by_hwmid
from .regions import classify_countries_matrix


def load_eobs_tx_country_cells(
    files: list[str | Path],
    countries: list[str],
    variable: str = "tx",
    temperature_unit: str = "degC",
) -> tuple[np.ndarray, pd.DatetimeIndex, np.ndarray, np.ndarray, np.ndarray]:
    """Load E-OBS daily Tmax for selected country cells only.

    The returned temperature array has shape ``(time, selected_cells)``.
    """

    daily_chunks = []
    date_chunks = []
    latitude = None
    longitude = None
    mask = None
    cell_lat = None
    cell_lon = None

    for file in files:
        path = Path(file)
        with nc.Dataset(path, "r") as dataset:
            time_name = _first_existing_variable(dataset, ("time",))
            latitude_name = _first_existing_variable(dataset, ("latitude", "lat"))
            longitude_name = _first_existing_variable(dataset, ("longitude", "lon"))
            if variable not in dataset.variables:
                raise KeyError(f"Variable {variable!r} not found in {path}")

            dates = _decode_time(dataset.variables[time_name])
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
                _load_daily_values_for_mask(
                    dataset.variables[variable],
                    mask,
                    temperature_unit=temperature_unit,
                )
            )
            date_chunks.append(dates)

    if mask is None or cell_lat is None or cell_lon is None:
        raise ValueError("No E-OBS files were provided")

    daily_tmax = np.vstack(daily_chunks)
    dates = pd.DatetimeIndex(np.concatenate([chunk.to_numpy() for chunk in date_chunks]))
    order = np.argsort(dates.to_numpy())
    return daily_tmax[order, :], pd.DatetimeIndex(dates.to_numpy()[order]), cell_lat, cell_lon, mask


def rank_eobs_tx_files(
    files: list[str | Path],
    countries: list[str],
    top_years: int = 10,
    ref_period: tuple[int, int] = (1981, 2010),
    min_heatwave_days: int = 3,
    threshold_quantile: float = 0.90,
    variable: str = "tx",
    temperature_unit: str = "degC",
    min_valid_days_per_year: int = 300,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Rank years by HWMId over country-mask cells from E-OBS daily files."""

    daily_tmax, dates, _cell_lat, _cell_lon, mask = load_eobs_tx_country_cells(
        files,
        countries=countries,
        variable=variable,
        temperature_unit=temperature_unit,
    )
    daily_tmax, dates, coverage = filter_years_by_data_coverage(
        daily_tmax,
        dates,
        min_valid_days_per_year=min_valid_days_per_year,
    )

    ranking = rank_daily_cells_by_hwmid(
        daily_tmax=daily_tmax,
        dates=dates,
        top_years=top_years,
        ref_period=ref_period,
        min_heatwave_days=min_heatwave_days,
        threshold_quantile=threshold_quantile,
    )
    ranking["country_cells"] = int(mask.sum())
    ranking["countries"] = "+".join(countries)
    ranking["source_file_count"] = len(files)
    ranking["source_file_names"] = ";".join(Path(file).name for file in files)
    return ranking, coverage


def filter_years_by_data_coverage(
    daily_tmax: np.ndarray,
    dates: pd.DatetimeIndex,
    min_valid_days_per_year: int = 300,
) -> tuple[np.ndarray, pd.DatetimeIndex, pd.DataFrame]:
    """Drop years with too few valid selected-cell days and report coverage."""

    rows = []
    keep_years = []
    for year in sorted(pd.DatetimeIndex(dates).year.unique()):
        year_mask = dates.year == year
        year_data = daily_tmax[year_mask, :]
        valid_days = int(np.count_nonzero(np.isfinite(year_data).any(axis=1)))
        total_days = int(np.count_nonzero(year_mask))
        complete = valid_days >= min_valid_days_per_year
        rows.append(
            {
                "year": int(year),
                "days_in_file": total_days,
                "valid_days_selected_cells": valid_days,
                "included_in_ranking": bool(complete),
            }
        )
        if complete:
            keep_years.append(year)

    keep_mask = np.isin(dates.year, keep_years)
    return daily_tmax[keep_mask, :], pd.DatetimeIndex(dates[keep_mask]), pd.DataFrame(rows)


def _load_daily_values_for_mask(variable, mask: np.ndarray, temperature_unit: str) -> np.ndarray:
    if not mask.any():
        raise ValueError("Country mask is empty")

    lat_positions = np.where(mask.any(axis=1))[0]
    lon_positions = np.where(mask.any(axis=0))[0]
    lat_slice = slice(int(lat_positions.min()), int(lat_positions.max()) + 1)
    lon_slice = slice(int(lon_positions.min()), int(lon_positions.max()) + 1)
    submask = mask[lat_slice, lon_slice].ravel()

    raw = np.ma.masked_invalid(np.ma.array(variable[:, lat_slice, lon_slice], copy=True))
    daily_box = raw.filled(np.nan).astype(np.float32)
    if temperature_unit == "K":
        daily_box = daily_box - np.float32(273.15)
    elif temperature_unit != "degC":
        raise ValueError(f"Unsupported temperature unit: {temperature_unit!r}")

    return daily_box.reshape(daily_box.shape[0], -1)[:, submask]
