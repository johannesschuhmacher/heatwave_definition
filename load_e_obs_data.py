"""Compatibility wrapper for the public package API."""

from heatwave_definition.io import load_e_obs_tmax


def load_e_obs_data(filename):
    return load_e_obs_tmax(filename).as_tuple()


__all__ = ["load_e_obs_data"]
