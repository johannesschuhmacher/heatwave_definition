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
