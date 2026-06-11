"""Scenario-year ranking helpers."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from .regions import classify_countries_matrix


def latitude_area_weights(latitude, longitude) -> np.ndarray:
    """Return relative grid-cell area weights for a regular lon-lat grid."""

    lat_weights = np.cos(np.deg2rad(np.asarray(latitude, dtype=float)))
    return np.repeat(lat_weights[:, None], len(longitude), axis=1)


def rank_years_by_hwmid(
    latitude,
    longitude,
    hwmid: np.ndarray,
    datetime_vector,
    no_years: int | None = None,
    countries=("Germany", "France"),
) -> pd.DataFrame:
    """Rank years by summed grid-cell HWMId inside the country mask."""

    return rank_years_by_grid_metric(
        latitude,
        longitude,
        hwmid,
        datetime_vector,
        no_years=no_years,
        countries=countries,
        aggregation="sum",
        score_column="hwmid_sum",
    )


def rank_years_by_grid_metric(
    latitude,
    longitude,
    metric: np.ndarray,
    datetime_vector,
    no_years: int | None = None,
    countries=("Germany", "France"),
    aggregation: str = "sum",
    score_column: str = "score",
) -> pd.DataFrame:
    """Rank years by an aggregated grid-cell metric inside a country mask."""

    years = np.array(sorted(pd.DatetimeIndex(datetime_vector).year.unique()), dtype=int)
    if metric.shape[-1] != len(years):
        raise ValueError("metric year dimension does not match datetime_vector years")

    mask = classify_countries_matrix(latitude, longitude, countries)
    if not mask.any():
        raise ValueError(f"Country mask is empty for {countries!r}")

    scores = aggregate_grid_metric(latitude, longitude, metric, mask, aggregation)
    order = np.argsort(scores)[::-1]
    if no_years is not None:
        order = order[: int(no_years)]

    return pd.DataFrame(
        {
            "rank": np.arange(1, len(order) + 1),
            "year": years[order],
            score_column: scores[order],
            "country_cells": int(mask.sum()),
            "aggregation": aggregation,
        }
    )


def aggregate_grid_metric(latitude, longitude, metric: np.ndarray, mask: np.ndarray, aggregation: str) -> np.ndarray:
    """Aggregate a `(lat, lon, year)` metric over a mask."""

    values = np.asarray(metric, dtype=float)[mask, :]
    if aggregation == "sum":
        return np.nansum(values, axis=0)
    if aggregation == "mean":
        return np.nanmean(values, axis=0)
    if aggregation == "max":
        return np.nanmax(values, axis=0)
    if aggregation == "area_weighted_mean":
        weights = latitude_area_weights(latitude, longitude)[mask]
        finite = np.isfinite(values)
        weighted = np.where(finite, values * weights[:, None], 0.0)
        denominator = np.sum(np.where(finite, weights[:, None], 0.0), axis=0)
        return np.divide(
            np.sum(weighted, axis=0),
            denominator,
            out=np.full(values.shape[1], np.nan, dtype=float),
            where=denominator > 0,
        )
    raise ValueError(f"Unsupported aggregation: {aggregation!r}")


def rank_years_by_country_weighted_hwmid(
    latitude,
    longitude,
    hwmid: np.ndarray,
    datetime_vector,
    country_weights: dict[str, float],
    no_years: int | None = None,
) -> pd.DataFrame:
    """Rank years by country-weighted mean HWMId.

    Each country weight is distributed over area-weighted cells of that country.
    This is intended for capacity- or renewable-weighted sensitivity checks
    where the weights are known at country level.
    """

    years = np.array(sorted(pd.DatetimeIndex(datetime_vector).year.unique()), dtype=int)
    if hwmid.shape[-1] != len(years):
        raise ValueError("hwmid year dimension does not match datetime_vector years")
    if not country_weights:
        raise ValueError("country_weights must not be empty")

    cell_weights = np.zeros(hwmid.shape[:2], dtype=float)
    area_weights = latitude_area_weights(latitude, longitude)
    for country, weight in country_weights.items():
        if weight <= 0:
            continue
        mask = classify_countries_matrix(latitude, longitude, [country])
        if not mask.any():
            raise ValueError(f"Country mask is empty for {country!r}")
        normalized_area = area_weights[mask] / float(np.nansum(area_weights[mask]))
        cell_weights[mask] += float(weight) * normalized_area

    if not np.isfinite(cell_weights).any() or np.nansum(cell_weights) <= 0:
        raise ValueError("country_weights produced an empty grid-cell weighting")
    cell_weights = cell_weights / np.nansum(cell_weights)

    scores = np.nansum(hwmid * cell_weights[:, :, None], axis=(0, 1))
    order = np.argsort(scores)[::-1]
    if no_years is not None:
        order = order[: int(no_years)]

    return pd.DataFrame(
        {
            "rank": np.arange(1, len(order) + 1),
            "year": years[order],
            "weighted_hwmid": scores[order],
            "weighted_countries": "+".join(country_weights.keys()),
        }
    )


def write_ranked_years(path: str | Path, ranking: pd.DataFrame) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    ranking.to_csv(path, index=False)
