"""Compatibility wrapper for the public package API."""

from heatwave_definition.io import load_copernicus_tasadjust_daily_tmax


def load_copernicus(filename):
    return load_copernicus_tasadjust_daily_tmax(filename).as_tuple()


__all__ = ["load_copernicus"]
