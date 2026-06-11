"""Compatibility wrapper for the public package API."""

from heatwave_definition.ranking import rank_years_by_hwmid as _rank_years_by_hwmid


def rank_years_by_hwmid(latitude, longitude, hwmid, datetime_vector, no_years):
    ranking = _rank_years_by_hwmid(
        latitude,
        longitude,
        hwmid,
        datetime_vector,
        no_years=no_years,
        countries=("Germany", "France"),
    )
    return ranking["year"].to_numpy()


__all__ = ["rank_years_by_hwmid"]
