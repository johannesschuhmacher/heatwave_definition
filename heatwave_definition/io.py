"""NetCDF loading helpers for daily Tmax data."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import netCDF4 as nc
import numpy as np
import pandas as pd


TemperatureUnit = Literal["K", "degC"]


@dataclass(frozen=True)
class DailyTemperatureData:
    dates: pd.DatetimeIndex
    longitude: np.ndarray
    latitude: np.ndarray
    max_daily_temp: np.ma.MaskedArray

    def as_tuple(self):
        return self.dates, self.longitude, self.latitude, self.max_daily_temp


def load_e_obs_tmax(
    filename: str | Path,
    variable: str = "tx",
    temperature_unit: TemperatureUnit = "degC",
) -> DailyTemperatureData:
    """Load daily maximum temperature from an E-OBS NetCDF file."""

    with nc.Dataset(filename, "r") as data:
        time_var = data.variables["time"]
        dates = _decode_time(time_var)
        longitude = np.array(data.variables["longitude"][:])
        latitude = np.array(data.variables["latitude"][:])
        temp = np.ma.masked_invalid(np.ma.array(data.variables[variable][:], copy=True))

    return DailyTemperatureData(
        dates=dates,
        longitude=longitude,
        latitude=latitude,
        max_daily_temp=_convert_temperature(temp, temperature_unit),
    )


def load_copernicus_tasadjust_daily_tmax(
    filename: str | Path,
    variable: str = "tasAdjust",
    temperature_unit: TemperatureUnit = "K",
) -> DailyTemperatureData:
    """Load Copernicus/CORDEX 3-hourly temperature and aggregate to daily Tmax."""

    with nc.Dataset(filename, "r") as data:
        time_var = data.variables["time"]
        timestamps = _decode_time(time_var)
        day_index = timestamps.floor("D")
        daily_dates = pd.DatetimeIndex(pd.unique(day_index))
        longitude = np.array(data.variables["lon"][:])
        latitude = np.array(data.variables["lat"][:])
        temp_var = data.variables[variable]

        daily = np.ma.masked_all((len(daily_dates), len(latitude), len(longitude)), dtype=float)
        day_to_pos = {day: pos for pos, day in enumerate(daily_dates)}

        for year in sorted(pd.unique(day_index.year)):
            year_step_idx = np.where(day_index.year == year)[0]
            if len(year_step_idx) == 0:
                continue
            temp_year = np.ma.masked_invalid(np.ma.array(temp_var[year_step_idx, :, :], copy=True))
            days_in_year = day_index[year_step_idx]
            for day in pd.DatetimeIndex(pd.unique(days_in_year)):
                local_idx = np.where(days_in_year == day)[0]
                daily[day_to_pos[day], :, :] = np.ma.max(temp_year[local_idx, :, :], axis=0)

    return DailyTemperatureData(
        dates=daily_dates,
        longitude=longitude,
        latitude=latitude,
        max_daily_temp=_convert_temperature(daily, temperature_unit),
    )


def load_era5_t2m_daily_tmax(
    input_path: str | Path,
    variable: str = "t2m",
    temperature_unit: TemperatureUnit = "K",
    pattern: str = "t2m_era5_*.nc",
) -> DailyTemperatureData:
    """Load ERA5 hourly 2 m temperature files and aggregate to daily Tmax.

    `input_path` may be either one NetCDF file or a directory containing yearly
    ERA5 files such as `t2m_era5_2011.nc`.
    """

    files = _resolve_input_files(input_path, pattern)
    date_chunks: list[pd.DatetimeIndex] = []
    temp_chunks: list[np.ma.MaskedArray] = []
    latitude: np.ndarray | None = None
    longitude: np.ndarray | None = None

    for path in files:
        with nc.Dataset(path, "r") as data:
            time_name = _first_existing_variable(data, ("valid_time", "time"))
            latitude_name = _first_existing_variable(data, ("latitude", "lat"))
            longitude_name = _first_existing_variable(data, ("longitude", "lon"))
            if variable not in data.variables:
                raise KeyError(f"Variable {variable!r} not found in {path}")

            timestamps = _decode_time(data.variables[time_name])
            day_index = timestamps.floor("D")
            daily_dates = pd.DatetimeIndex(pd.unique(day_index))
            file_latitude = np.array(data.variables[latitude_name][:])
            file_longitude = np.array(data.variables[longitude_name][:])

            if latitude is None:
                latitude = file_latitude
                longitude = file_longitude
            elif not (np.array_equal(latitude, file_latitude) and np.array_equal(longitude, file_longitude)):
                raise ValueError(f"Grid coordinates changed in {path}")

            temp_var = data.variables[variable]
            daily = np.ma.masked_all((len(daily_dates), len(file_latitude), len(file_longitude)), dtype=np.float32)
            for pos, day in enumerate(daily_dates):
                hourly_idx = np.where(day_index == day)[0]
                if len(hourly_idx):
                    hourly = np.ma.masked_invalid(np.ma.array(temp_var[hourly_idx, :, :], copy=True))
                    daily[pos, :, :] = np.ma.max(hourly, axis=0)

        date_chunks.append(daily_dates)
        temp_chunks.append(daily)

    if latitude is None or longitude is None:
        raise ValueError(f"No ERA5 input files found at {input_path}")

    dates = pd.DatetimeIndex(np.concatenate([chunk.to_numpy() for chunk in date_chunks]))
    daily_tmax = np.ma.concatenate(temp_chunks, axis=0)
    order = np.argsort(dates.to_numpy())
    dates = pd.DatetimeIndex(dates.to_numpy()[order])
    daily_tmax = daily_tmax[order, :, :]

    return DailyTemperatureData(
        dates=dates,
        longitude=longitude,
        latitude=latitude,
        max_daily_temp=_convert_temperature(daily_tmax, temperature_unit),
    )


def _decode_time(time_var) -> pd.DatetimeIndex:
    units = getattr(time_var, "units", None)
    if units is None:
        raise ValueError("NetCDF time variable has no 'units' attribute")
    calendar = getattr(time_var, "calendar", "standard")
    decoded = nc.num2date(
        time_var[:],
        units=units,
        calendar=calendar,
        only_use_cftime_datetimes=False,
        only_use_python_datetimes=False,
    )
    return pd.DatetimeIndex(pd.to_datetime([_isoformat_time(value) for value in decoded]))


def _isoformat_time(value) -> str:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _convert_temperature(temp: np.ma.MaskedArray, unit: TemperatureUnit) -> np.ma.MaskedArray:
    if unit == "K":
        return temp - 273.15
    if unit == "degC":
        return temp
    raise ValueError(f"Unsupported temperature unit: {unit!r}")


def _resolve_input_files(input_path: str | Path, pattern: str) -> list[Path]:
    path = Path(input_path)
    if path.is_dir():
        files = sorted(path.glob(pattern))
    elif path.is_file():
        files = [path]
    else:
        raise FileNotFoundError(f"Input path does not exist: {path}")
    if not files:
        raise FileNotFoundError(f"No files matching {pattern!r} found in {path}")
    return files


def _first_existing_variable(dataset: nc.Dataset, candidates: tuple[str, ...]) -> str:
    for candidate in candidates:
        if candidate in dataset.variables:
            return candidate
    raise KeyError(f"None of {candidates!r} found in NetCDF variables")
