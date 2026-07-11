"""HWMId-based heatwave scenario definition tools."""

from .hwmid import HWMidResult, calc_hwmid
from .ranking import (
    latitude_area_weights,
    rank_years_by_cell_weighted_hwmid,
    rank_years_by_country_weighted_hwmid,
    rank_years_by_grid_metric,
    rank_years_by_hwmid,
)
from .regions import classify_countries_matrix, normalize_country_names

__all__ = [
    "DailyTemperatureData",
    "HWMidResult",
    "calc_hwmid",
    "classify_countries_matrix",
    "load_copernicus_tasadjust_daily_tmax",
    "load_e_obs_tmax",
    "load_era5_t2m_daily_tmax",
    "latitude_area_weights",
    "rank_years_by_cell_weighted_hwmid",
    "normalize_country_names",
    "rank_years_by_country_weighted_hwmid",
    "rank_years_by_grid_metric",
    "rank_years_by_hwmid",
]


def __getattr__(name):
    if name in {
        "DailyTemperatureData",
        "load_copernicus_tasadjust_daily_tmax",
        "load_e_obs_tmax",
        "load_era5_t2m_daily_tmax",
    }:
        from . import io

        return getattr(io, name)
    raise AttributeError(name)
