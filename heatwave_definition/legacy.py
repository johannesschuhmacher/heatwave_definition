"""Compatibility helpers for trusted legacy result files."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import pickle

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class LegacyMetricsData:
    hwmid: np.ndarray
    temp_anomaly: np.ndarray | None
    heatwave_duration: np.ndarray | None
    annual_tmax: np.ndarray | None
    longitude: np.ndarray
    latitude: np.ndarray
    dates: pd.DatetimeIndex


def load_legacy_metrics_pickle(filename: str | Path) -> LegacyMetricsData:
    """Load trusted legacy metric pickles created by the exploratory scripts.

    Pickle files can execute arbitrary code when loaded. This helper is only
    for local, trusted legacy files and exists only to make archived exploratory
    results traceable.
    """

    with Path(filename).open("rb") as handle:
        obj = pickle.load(handle)

    if not isinstance(obj, (list, tuple)) or len(obj) < 9:
        raise ValueError("Legacy metrics pickle has an unsupported structure")

    hwmid = np.asarray(obj[0])
    temp_anomaly = _array_or_none(obj, 1)
    heatwave_duration = _array_or_none(obj, 2)
    annual_tmax = _array_or_none(obj, 4)
    if len(obj) >= 12 and isinstance(obj[6], dict):
        longitude = np.asarray(obj[7])
        latitude = np.asarray(obj[8])
        dates = pd.DatetimeIndex(obj[9])
    else:
        longitude = np.asarray(obj[6])
        latitude = np.asarray(obj[7])
        dates = pd.DatetimeIndex(obj[8])

    if hwmid.ndim != 3:
        raise ValueError("Legacy HWMId array must be three-dimensional")
    if hwmid.shape[:2] != (len(latitude), len(longitude)):
        raise ValueError("Legacy HWMId grid dimensions do not match latitude/longitude")
    for name, array in {
        "temp_anomaly": temp_anomaly,
        "heatwave_duration": heatwave_duration,
        "annual_tmax": annual_tmax,
    }.items():
        if array is not None and array.shape != hwmid.shape:
            raise ValueError(f"Legacy {name} array does not match HWMId shape")

    years = np.array(sorted(dates.year.unique()), dtype=int)
    if hwmid.shape[-1] != len(years):
        raise ValueError("Legacy HWMId year dimension does not match datetime years")

    return LegacyMetricsData(
        hwmid=hwmid,
        temp_anomaly=temp_anomaly,
        heatwave_duration=heatwave_duration,
        annual_tmax=annual_tmax,
        longitude=longitude,
        latitude=latitude,
        dates=dates,
    )


def _array_or_none(obj: list | tuple, index: int) -> np.ndarray | None:
    if len(obj) <= index or obj[index] is None:
        return None
    array = np.asarray(obj[index])
    return array if array.ndim == 3 else None
