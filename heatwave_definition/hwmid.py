"""Heat Wave Magnitude Index daily (HWMId) calculation.

The implementation follows the method described by Russo et al. (2015):
threshold exceedance over a 31-day calendar window, a minimum run length of
three days, and daily magnitudes normalized by the reference-period annual
maximum-temperature interquartile range.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import numpy as np
import pandas as pd


HWMID_METHOD_ID = "russo2015-noleap365-v1"


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
    _validate_hwmid_parameters(ref_start, ref_end, min_heatwave_days, threshold_quantile)
    _validate_daily_time_axis(dates)

    noleap_mask = _noleap_mask(dates)
    dates = dates[noleap_mask]
    max_daily_temp = np.ma.array(max_daily_temp, copy=False)[noleap_mask, ...]
    _validate_reference_period(dates, ref_start, ref_end)

    lat_count = len(latitude)
    lon_count = len(longitude)
    years = np.array(sorted(dates.year.unique()), dtype=int)
    year_count = len(years)
    year_to_pos = {year: idx for idx, year in enumerate(years)}
    day_of_year = _noleap_day_of_year(dates)

    tmax = np.ma.masked_invalid(np.ma.array(max_daily_temp, copy=False))

    hwmid = np.full((lat_count, lon_count, year_count), np.nan)
    temp_anomaly = np.full_like(hwmid, np.nan, dtype=float)
    annual_tmax = np.full_like(hwmid, np.nan, dtype=float)
    heatwave_duration = np.full_like(hwmid, np.nan, dtype=float)
    temperature_threshold = np.full((lat_count, lon_count, 365), np.nan)
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
            runs = _find_runs(above_threshold, min_heatwave_days, dates=dates)

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
                        "start_day": float(day_of_year[start_idx]),
                        "start_index": float(day_of_year[start_idx] - 1),
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
    """Build the 365 centered 31-day threshold samples used by HWMId.

    Leap days must be removed before calling this helper. The preceding and
    following calendar years provide the boundary days needed for January and
    December windows.
    """

    dates = pd.DatetimeIndex(dates)
    if np.any(~_noleap_mask(dates)):
        raise ValueError("Remove 29 February before building HWMId threshold windows")

    positions = np.arange(len(dates))
    day_of_year = _noleap_day_of_year(dates)
    serial_day = _noleap_serial_day(dates)
    all_masks: list[list[int]] = [[] for _ in range(365)]

    for year in ref_years:
        for target_day in range(1, 366):
            center = positions[(dates.year == year) & (day_of_year == target_day)]
            if len(center) != 1:
                raise ValueError(
                    f"Reference year {year} does not contain exactly one no-leap "
                    f"calendar day {target_day}"
                )
            center_pos = int(center[0])
            distance = serial_day - serial_day[center_pos]
            window = positions[(distance >= -15) & (distance <= 15)]
            if len(window) != 31:
                raise ValueError(
                    f"Incomplete 31-day threshold window around year {year}, "
                    f"calendar day {target_day}; include the years before and after "
                    "the reference period"
                )
            all_masks[target_day - 1].extend(int(value) for value in window)

    return [np.asarray(mask, dtype=int) for mask in all_masks]


def _find_runs(
    flags: np.ndarray,
    min_length: int,
    dates: pd.DatetimeIndex | None = None,
) -> list[tuple[int, int]]:
    """Return inclusive runs, splitting them at non-consecutive calendar days."""

    flags = np.asarray(flags, dtype=bool)
    if min_length < 1:
        raise ValueError("min_length must be at least one")
    continuity = np.ones(len(flags), dtype=bool)
    if dates is not None:
        dates = pd.DatetimeIndex(dates)
        if len(dates) != len(flags):
            raise ValueError("dates length must match flags length")
        serial_day = _noleap_serial_day(dates)
        continuity[1:] = np.diff(serial_day) == 1

    runs: list[tuple[int, int]] = []
    start = None
    for idx, flag in enumerate(flags):
        if idx and not continuity[idx] and start is not None:
            if idx - start >= min_length:
                runs.append((start, idx - 1))
            start = None
        if flag and start is None:
            start = idx
        elif not flag and start is not None:
            if idx - start >= min_length:
                runs.append((start, idx - 1))
            start = None
    if start is not None and len(flags) - start >= min_length:
        runs.append((start, len(flags) - 1))
    return runs


def _noleap_mask(dates: pd.DatetimeIndex) -> np.ndarray:
    """Return a mask that excludes 29 February."""

    dates = pd.DatetimeIndex(dates)
    return ~((dates.month == 2) & (dates.day == 29))


def _noleap_day_of_year(dates: pd.DatetimeIndex) -> np.ndarray:
    """Return one-based day numbers on a 365-day calendar."""

    dates = pd.DatetimeIndex(dates)
    if np.any(~_noleap_mask(dates)):
        raise ValueError("29 February has no day number on the HWMId no-leap calendar")
    day_of_year = dates.dayofyear.to_numpy(dtype=int)
    after_february = dates.is_leap_year & (dates.month > 2)
    return day_of_year - np.asarray(after_february, dtype=int)


def _noleap_serial_day(dates: pd.DatetimeIndex) -> np.ndarray:
    """Return continuous integer days for no-leap calendar comparisons."""

    dates = pd.DatetimeIndex(dates)
    return dates.year.to_numpy(dtype=int) * 365 + _noleap_day_of_year(dates)


def _validate_hwmid_parameters(
    ref_start: int,
    ref_end: int,
    min_heatwave_days: int,
    threshold_quantile: float,
) -> None:
    if ref_start > ref_end:
        raise ValueError("reference-period start year must not exceed end year")
    if min_heatwave_days < 1:
        raise ValueError("min_heatwave_days must be at least one")
    if not 0.0 < threshold_quantile < 1.0:
        raise ValueError("threshold_quantile must be between zero and one")


def _validate_daily_time_axis(dates: pd.DatetimeIndex) -> None:
    if dates.hasnans:
        raise ValueError("datetime_vector must not contain missing timestamps")
    if not dates.is_unique:
        raise ValueError("datetime_vector must not contain duplicate timestamps")
    if not dates.is_monotonic_increasing:
        raise ValueError("datetime_vector must be sorted in increasing order")
    if np.any(dates != dates.floor("D")):
        raise ValueError("datetime_vector must contain daily timestamps")


def _validate_reference_period(dates: pd.DatetimeIndex, ref_start: int, ref_end: int) -> None:
    day_of_year = _noleap_day_of_year(dates)
    for year in range(ref_start, ref_end + 1):
        present = np.unique(day_of_year[dates.year == year])
        if len(present) != 365 or present[0] != 1 or present[-1] != 365:
            raise ValueError(f"Reference year {year} is incomplete on the 365-day calendar")


def canonical_day_of_year(month: int, day: int) -> int:
    """Return day-of-year on the 365-day HWMId calendar."""

    if month == 2 and day == 29:
        raise ValueError("29 February is excluded from the HWMId calendar")
    return pd.Timestamp(2001, month, day).dayofyear
