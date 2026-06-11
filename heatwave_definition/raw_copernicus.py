"""Memory-aware ranking from Copernicus/CORDEX tasAdjust NetCDF files."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import warnings

import netCDF4 as nc
import numpy as np
import pandas as pd

from .hwmid import _build_threshold_masks, _find_runs
from .io import _decode_time
from .regions import classify_countries_matrix


@dataclass(frozen=True)
class CopernicusRun:
    label: str
    scenario: str
    driving_model: str
    regional_model: str
    path: Path


def discover_tasadjust_runs(root: str | Path) -> list[CopernicusRun]:
    """Discover full-period tasAdjust files below a Copernicus2100 root."""

    root = Path(root)
    runs: list[CopernicusRun] = []
    for path in sorted(root.rglob("tasAdjust*.nc")):
        lower_parts = {part.lower() for part in path.parts}
        if "yearly" in lower_parts or "daten_max" in lower_parts:
            continue

        parsed = parse_tasadjust_filename(path)
        if parsed is None:
            continue
        runs.append(parsed)
    return runs


def parse_tasadjust_filename(path: str | Path) -> CopernicusRun | None:
    path = Path(path)
    parts = path.name.split("_")
    if len(parts) < 8 or parts[0] != "tasAdjust":
        return None

    driving_model = parts[2]
    scenario = parts[3].upper().replace("RCP", "RCP")
    regional_model = parts[5]
    label = f"{driving_model} / {regional_model} {scenario}"
    return CopernicusRun(
        label=label,
        scenario=scenario,
        driving_model=driving_model,
        regional_model=regional_model,
        path=path,
    )


def rank_copernicus_tasadjust_file(
    path: str | Path,
    countries: list[str],
    top_years: int = 10,
    ref_period: tuple[int, int] = (1981, 2010),
    min_heatwave_days: int = 3,
    threshold_quantile: float = 0.90,
    variable: str = "tasAdjust",
    temperature_unit: str = "K",
) -> pd.DataFrame:
    """Rank years by summed HWMId over a country mask without loading Europe-wide arrays."""

    path = Path(path)
    with nc.Dataset(path, "r") as dataset:
        dates_3h = _decode_time(dataset.variables["time"])
        day_index = dates_3h.floor("D")
        daily_dates = pd.DatetimeIndex(pd.unique(day_index))
        latitude = np.asarray(dataset.variables["lat"][:])
        longitude = np.asarray(dataset.variables["lon"][:])
        mask = classify_countries_matrix(latitude, longitude, countries)
        daily_tmax = _load_daily_tmax_for_mask(
            dataset.variables[variable],
            dates_3h,
            day_index,
            daily_dates,
            mask,
            temperature_unit=temperature_unit,
        )

    ranking = rank_daily_cells_by_hwmid(
        daily_tmax=daily_tmax,
        dates=daily_dates,
        top_years=top_years,
        ref_period=ref_period,
        min_heatwave_days=min_heatwave_days,
        threshold_quantile=threshold_quantile,
    )
    ranking["country_cells"] = int(mask.sum())
    ranking["countries"] = "+".join(countries)
    ranking["source_file"] = str(path)
    return ranking


def rank_daily_cells_by_hwmid(
    daily_tmax: np.ndarray,
    dates: pd.DatetimeIndex,
    top_years: int = 10,
    ref_period: tuple[int, int] = (1981, 2010),
    min_heatwave_days: int = 3,
    threshold_quantile: float = 0.90,
    weights: np.ndarray | None = None,
) -> pd.DataFrame:
    """Calculate HWMId for selected cells and return a ranked year table."""

    dates = pd.DatetimeIndex(dates)
    if daily_tmax.shape[0] != len(dates):
        raise ValueError("daily_tmax time dimension must match dates")
    if daily_tmax.ndim != 2:
        raise ValueError("daily_tmax must have shape (time, cells)")

    years = np.array(sorted(dates.year.unique()), dtype=int)
    year_to_pos = {year: idx for idx, year in enumerate(years)}
    year_masks = {year: dates.year == year for year in years}
    ref_start, ref_end = ref_period
    ref_years = list(range(int(ref_start), int(ref_end) + 1))
    ref_masks = {
        year: (dates >= pd.Timestamp(year, 1, 1))
        & (dates <= pd.Timestamp(year, 12, 31))
        for year in ref_years
    }

    cell_count = daily_tmax.shape[1]
    thresholds = np.full((366, cell_count), np.nan, dtype=np.float32)
    threshold_masks = _build_threshold_masks(dates, ref_years)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=RuntimeWarning)
        for day, idx in enumerate(threshold_masks):
            if len(idx):
                thresholds[day, :] = np.nanquantile(
                    daily_tmax[idx, :],
                    threshold_quantile,
                    axis=0,
                )

        ref_annual_max = np.vstack(
            [
                np.nanmax(daily_tmax[ref_masks[year], :], axis=0)
                for year in ref_years
            ]
        )

    denominator = np.nanquantile(ref_annual_max, 0.75, axis=0) - np.nanquantile(
        ref_annual_max,
        0.25,
        axis=0,
    )
    t25 = np.nanquantile(ref_annual_max, 0.25, axis=0)
    valid_cells = np.isfinite(denominator) & (denominator > 0)

    hwmid_cells = np.zeros((cell_count, len(years)), dtype=np.float32)
    day_of_year = dates.dayofyear.to_numpy()
    for cell in range(cell_count):
        if not valid_cells[cell]:
            continue
        series = daily_tmax[:, cell].astype(float, copy=False)
        daily_thresholds = thresholds[day_of_year - 1, cell]
        above_threshold = np.isfinite(series) & (series > daily_thresholds)

        for start_idx, end_idx in _find_runs(above_threshold, min_heatwave_days):
            event_values = series[start_idx : end_idx + 1]
            daily_magnitude = np.where(
                event_values > t25[cell],
                (event_values - t25[cell]) / denominator[cell],
                0.0,
            )
            magnitude = float(np.nansum(daily_magnitude))
            start_year = int(dates[start_idx].year)
            year_pos = year_to_pos.get(start_year)
            if year_pos is not None and magnitude > hwmid_cells[cell, year_pos]:
                hwmid_cells[cell, year_pos] = magnitude

    if weights is None:
        scores = np.nansum(hwmid_cells, axis=0)
    else:
        weights = np.asarray(weights, dtype=float)
        if weights.shape != (cell_count,):
            raise ValueError("weights must have one value per selected cell")
        scores = np.nansum(hwmid_cells * weights[:, None], axis=0)

    order = np.argsort(scores)[::-1][:top_years]
    return pd.DataFrame(
        {
            "rank": np.arange(1, len(order) + 1),
            "year": years[order],
            "hwmid_sum": scores[order],
        }
    )


def _load_daily_tmax_for_mask(
    variable,
    timestamps: pd.DatetimeIndex,
    day_index: pd.DatetimeIndex,
    daily_dates: pd.DatetimeIndex,
    mask: np.ndarray,
    temperature_unit: str,
) -> np.ndarray:
    if not mask.any():
        raise ValueError("Country mask is empty")

    lat_positions = np.where(mask.any(axis=1))[0]
    lon_positions = np.where(mask.any(axis=0))[0]
    lat_slice = slice(int(lat_positions.min()), int(lat_positions.max()) + 1)
    lon_slice = slice(int(lon_positions.min()), int(lon_positions.max()) + 1)
    submask = mask[lat_slice, lon_slice].ravel()

    daily = np.full((len(daily_dates), int(submask.sum())), np.nan, dtype=np.float32)
    day_to_pos = {day: pos for pos, day in enumerate(daily_dates)}

    for year in sorted(pd.unique(timestamps.year)):
        year_steps = np.where(timestamps.year == year)[0]
        if not len(year_steps):
            continue

        days_in_year = day_index[year_steps]
        unique_days = pd.DatetimeIndex(pd.unique(days_in_year))
        if len(year_steps) % len(unique_days) != 0:
            raise ValueError(f"Unexpected non-regular time step count in year {year}")

        steps_per_day = len(year_steps) // len(unique_days)
        raw = np.ma.masked_invalid(
            np.ma.array(
                variable[int(year_steps[0]) : int(year_steps[-1]) + 1, lat_slice, lon_slice],
                copy=True,
            )
        )
        raw = raw.reshape((len(unique_days), steps_per_day, raw.shape[1], raw.shape[2]))
        daily_box = np.ma.max(raw, axis=1).filled(np.nan).astype(np.float32)
        if temperature_unit == "K":
            daily_box = daily_box - np.float32(273.15)
        elif temperature_unit != "degC":
            raise ValueError(f"Unsupported temperature unit: {temperature_unit!r}")

        daily_positions = [day_to_pos[day] for day in unique_days]
        daily[np.asarray(daily_positions), :] = daily_box.reshape(len(unique_days), -1)[:, submask]

    return daily
