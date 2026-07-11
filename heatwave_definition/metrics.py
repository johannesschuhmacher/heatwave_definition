"""Metric-array loading helpers for reproducible and legacy runs."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from .legacy import load_legacy_metrics_pickle


@dataclass(frozen=True)
class MetricsData:
    hwmid: np.ndarray
    temp_anomaly: np.ndarray | None
    heatwave_duration: np.ndarray | None
    annual_tmax: np.ndarray | None
    longitude: np.ndarray
    latitude: np.ndarray
    dates: pd.DatetimeIndex
    source_path: Path
    source_format: str


def load_metrics_file(path: str | Path) -> MetricsData:
    """Load deterministic `.npz` metrics or a trusted legacy `.pkl` file."""

    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == ".npz":
        return load_metrics_npz(path)
    if suffix == ".pkl":
        legacy = load_legacy_metrics_pickle(path)
        return MetricsData(
            hwmid=legacy.hwmid,
            temp_anomaly=legacy.temp_anomaly,
            heatwave_duration=legacy.heatwave_duration,
            annual_tmax=legacy.annual_tmax,
            longitude=legacy.longitude,
            latitude=legacy.latitude,
            dates=legacy.dates,
            source_path=path,
            source_format="legacy_pickle",
        )
    raise ValueError(f"Unsupported metrics file format: {path}")


def load_metrics_npz(path: str | Path) -> MetricsData:
    """Load metric arrays written by `python -m heatwave_definition.cli run`."""

    path = Path(path)
    with np.load(path, allow_pickle=False) as data:
        required = {"hwmid", "longitude", "latitude", "dates"}
        missing = required.difference(data.files)
        if missing:
            raise ValueError(f"Metrics npz is missing arrays: {sorted(missing)}")

        hwmid = np.asarray(data["hwmid"])
        longitude = np.asarray(data["longitude"])
        latitude = np.asarray(data["latitude"])
        dates = pd.to_datetime(np.asarray(data["dates"], dtype="int64"))
        temp_anomaly = _optional_array(data, "temp_anomaly")
        heatwave_duration = _optional_array(data, "heatwave_duration")
        annual_tmax = _optional_array(data, "annual_tmax")

    _validate_metric_shapes(
        hwmid=hwmid,
        latitude=latitude,
        longitude=longitude,
        dates=dates,
        arrays={
            "temp_anomaly": temp_anomaly,
            "heatwave_duration": heatwave_duration,
            "annual_tmax": annual_tmax,
        },
    )
    return MetricsData(
        hwmid=hwmid,
        temp_anomaly=temp_anomaly,
        heatwave_duration=heatwave_duration,
        annual_tmax=annual_tmax,
        longitude=longitude,
        latitude=latitude,
        dates=dates,
        source_path=path,
        source_format="npz",
    )


def resolve_metrics_file(directory: str | Path, candidates: str | list[str] | tuple[str, ...]) -> Path:
    """Return the first existing candidate metrics file in a directory."""

    directory = Path(directory)
    if isinstance(candidates, str):
        candidates = [candidates]
    attempted = []
    for candidate in candidates:
        path = directory / candidate
        attempted.append(path)
        if path.exists():
            return path
    formatted = "\n".join(f"- {path}" for path in attempted)
    raise FileNotFoundError(f"No metrics file found. Tried:\n{formatted}")


def _optional_array(data, name: str) -> np.ndarray | None:
    if name not in data.files:
        return None
    array = np.asarray(data[name])
    return array if array.ndim == 3 else None


def _validate_metric_shapes(
    hwmid: np.ndarray,
    latitude: np.ndarray,
    longitude: np.ndarray,
    dates: pd.DatetimeIndex,
    arrays: dict[str, np.ndarray | None],
) -> None:
    if hwmid.ndim != 3:
        raise ValueError("HWMId array must be three-dimensional")
    if hwmid.shape[:2] != (len(latitude), len(longitude)):
        raise ValueError("HWMId grid dimensions do not match latitude/longitude")
    years = np.array(sorted(dates.year.unique()), dtype=int)
    if hwmid.shape[-1] != len(years):
        raise ValueError("HWMId year dimension does not match datetime years")
    for name, array in arrays.items():
        if array is not None and array.shape != hwmid.shape:
            raise ValueError(f"{name} array does not match HWMId shape")
