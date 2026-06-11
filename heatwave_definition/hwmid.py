"""Heat Wave Magnitude Index daily (HWMId) calculation.

The implementation follows the method described by Russo et al. (2015):
threshold exceedance over a 31-day calendar window, a minimum run length of
three days, and daily magnitudes normalized by the reference-period annual
maximum-temperature interquartile range.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Iterable

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class HWMidResult:
    hwmid: np.ndarray
    temp_anomaly: np.ndarray
    heatwave_duration: np.ndarray
    temperature_threshold: np.ndarray
    annual_tmax: np.ndarray
    heatwave_start_day: np.ndarray
    heatwave_start_index: np.ndarray

    def as_tuple(self) -> tuple[np.ndarray, ...]:
        return (
            self.hwmid,
            self.temp_anomaly,
            self.heatwave_duration,
            self.temperature_threshold,
            self.annual_tmax,
            self.heatwave_start_day,
            self.heatwave_start_index,
        )


def calc_hwmid(
    max_daily_temp,
    latitude,
    longitude,
    datetime_vector,
    ref_period: Iterable[int] = (1981, 2010),
    min_heatwave_days: int = 3,
    threshold_quantile: float = 0.90,
) -> tuple[np.ndarray, ...]:
    """Calculate yearly strongest-event HWMId per grid cell.

    Parameters
    ----------
    max_daily_temp:
        Daily maximum temperature array with shape `(time, lat, lon)` in deg C.
        Plain NumPy arrays and masked arrays are supported.
    latitude, longitude:
        One-dimensional coordinate arrays.
    datetime_vector:
        Daily timestamps matching the first dimension of `max_daily_temp`.
    ref_period:
        Inclusive reference-period year range, default 1981-2010.
    min_heatwave_days:
        Minimum number of consecutive threshold exceedance days.
    threshold_quantile:
        Calendar-day threshold quantile in the 31-day moving window.

    Returns
    -------
    tuple
        `(hwmid, temp_anomaly, heatwave_duration, temperature_threshold,
        annual_tmax, heatwave_start_day, heatwave_start_index)`.
    """

    ref_start, ref_end = [int(x) for x in ref_period]
    dates = pd.DatetimeIndex(datetime_vector)
    if len(dates) != np.shape(max_daily_temp)[0]:
        raise ValueError("datetime_vector length must match max_daily_temp time dimension")

    lat_count = len(latitude)
    lon_count = len(longitude)
    years = np.array(sorted(dates.year.unique()), dtype=int)
    year_count = len(years)
    year_to_pos = {year: idx for idx, year in enumerate(years)}
    day_of_year = dates.dayofyear.to_numpy()

    tmax = np.ma.masked_invalid(np.ma.array(max_daily_temp, copy=False))

    hwmid = np.full((lat_count, lon_count, year_count), np.nan)
    temp_anomaly = np.full_like(hwmid, np.nan, dtype=float)
    annual_tmax = np.full_like(hwmid, np.nan, dtype=float)
    heatwave_duration = np.full_like(hwmid, np.nan, dtype=float)
    temperature_threshold = np.full((lat_count, lon_count, 366), np.nan)
    heatwave_start_day = np.full_like(hwmid, np.nan, dtype=float)
    heatwave_start_index = np.full_like(hwmid, np.nan, dtype=float)

    ref_years = list(range(ref_start, ref_end + 1))
    ref_masks = {
        year: (dates >= pd.Timestamp(year, 1, 1))
        & (dates <= pd.Timestamp(year, 12, 31))
        for year in ref_years
    }
    threshold_masks = _build_threshold_masks(dates, ref_years)
    year_masks = {year: dates.year == year for year in years}

    for lat_idx in range(lat_count):
        for lon_idx in range(lon_count):
            series = np.ma.filled(tmax[:, lat_idx, lon_idx], np.nan).astype(float)
            if not np.isfinite(series).any():
                continue

            ref_annual_max = _annual_reference_maxima(series, ref_masks)
            if np.count_nonzero(np.isfinite(ref_annual_max)) < 2:
                continue

            thresholds = np.array(
                [
                    np.nanquantile(series[idx], threshold_quantile)
                    if len(idx) and np.isfinite(series[idx]).any()
                    else np.nan
                    for idx in threshold_masks
                ],
                dtype=float,
            )
            temperature_threshold[lat_idx, lon_idx, :] = thresholds

            annual_max_values = np.array(
                [
                    np.nanmax(series[year_masks[year]])
                    if np.isfinite(series[year_masks[year]]).any()
                    else np.nan
                    for year in years
                ],
                dtype=float,
            )
            annual_tmax[lat_idx, lon_idx, :] = annual_max_values
            temp_anomaly[lat_idx, lon_idx, :] = annual_max_values - np.nanmean(ref_annual_max)

            denominator = np.nanquantile(ref_annual_max, 0.75) - np.nanquantile(ref_annual_max, 0.25)
            if not np.isfinite(denominator) or denominator <= 0:
                continue
            t25 = np.nanquantile(ref_annual_max, 0.25)

            daily_thresholds = thresholds[day_of_year - 1]
            above_threshold = np.isfinite(series) & (series > daily_thresholds)
            runs = _find_runs(above_threshold, min_heatwave_days)

            best_by_year: dict[int, dict[str, float | pd.Timestamp]] = {}
            for start_idx, end_idx in runs:
                days = slice(start_idx, end_idx + 1)
                event_values = series[days]
                daily_magnitude = np.where(
                    event_values > t25,
                    (event_values - t25) / denominator,
                    0.0,
                )
                magnitude = float(np.nansum(daily_magnitude))
                start_date = dates[start_idx]
                start_year = int(start_date.year)
                current = best_by_year.get(start_year)
                if current is None or magnitude > float(current["magnitude"]):
                    best_by_year[start_year] = {
                        "magnitude": magnitude,
                        "duration": float(end_idx - start_idx + 1),
                        "start_day": float(start_date.dayofyear),
                        "start_index": float(start_date.dayofyear - 1)
                        if start_date.dayofyear <= 365
                        else np.nan,
                    }

            hwmid[lat_idx, lon_idx, :] = 0.0
            heatwave_duration[lat_idx, lon_idx, :] = 0.0
            for year, values in best_by_year.items():
                pos = year_to_pos.get(year)
                if pos is None:
                    continue
                hwmid[lat_idx, lon_idx, pos] = float(values["magnitude"])
                heatwave_duration[lat_idx, lon_idx, pos] = float(values["duration"])
                heatwave_start_day[lat_idx, lon_idx, pos] = float(values["start_day"])
                heatwave_start_index[lat_idx, lon_idx, pos] = float(values["start_index"])

    return HWMidResult(
        hwmid=hwmid,
        temp_anomaly=temp_anomaly,
        heatwave_duration=heatwave_duration,
        temperature_threshold=temperature_threshold,
        annual_tmax=annual_tmax,
        heatwave_start_day=heatwave_start_day,
        heatwave_start_index=heatwave_start_index,
    ).as_tuple()


def _annual_reference_maxima(series: np.ndarray, ref_masks: dict[int, np.ndarray]) -> np.ndarray:
    maxima = []
    for mask in ref_masks.values():
        values = series[mask]
        maxima.append(np.nanmax(values) if np.isfinite(values).any() else np.nan)
    return np.array(maxima, dtype=float)


def _build_threshold_masks(dates: pd.DatetimeIndex, ref_years: list[int]) -> list[np.ndarray]:
    """Build 31-day moving-window masks for 366 calendar-day thresholds.

    This keeps the original Russo-style indexing used in the exploratory code:
    for each reference year, the source window spans Dec 17 of the previous year
    to Jan 16 of the next year, and day `d` uses columns `d:d+31`.
    """

    all_masks: list[list[int]] = [[] for _ in range(366)]
    positions = np.arange(len(dates))

    for year in ref_years:
        start = pd.Timestamp(year - 1, 12, 17)
        end = pd.Timestamp(year + 1, 1, 16)
        idx = positions[(dates >= start) & (dates <= end)]
        idx = idx[:396]
        for day in range(366):
            window = idx[day : day + 31]
            all_masks[day].extend(int(i) for i in window)

    return [np.array(sorted(set(mask)), dtype=int) for mask in all_masks]


def _find_runs(flags: np.ndarray, min_length: int) -> list[tuple[int, int]]:
    runs: list[tuple[int, int]] = []
    start = None
    for idx, flag in enumerate(flags):
        if flag and start is None:
            start = idx
        elif not flag and start is not None:
            if idx - start >= min_length:
                runs.append((start, idx - 1))
            start = None
    if start is not None and len(flags) - start >= min_length:
        runs.append((start, len(flags) - 1))
    return runs


def canonical_day_of_year(month: int, day: int) -> int:
    """Return day-of-year on a leap-year calendar."""

    return date(2000, month, day).timetuple().tm_yday
