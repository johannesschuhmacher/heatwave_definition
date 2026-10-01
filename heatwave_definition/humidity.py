"""Humidity-aware heat metrics used in sensitivity analyses."""

from __future__ import annotations

import numpy as np


def relative_humidity_from_temperature_and_dewpoint(
    temperature_k: np.ndarray,
    dewpoint_k: np.ndarray,
) -> np.ndarray:
    """Return relative humidity in percent using the Magnus equation."""

    temperature_c = np.asarray(temperature_k, dtype=float) - 273.15
    dewpoint_c = np.asarray(dewpoint_k, dtype=float) - 273.15
    exponent = (
        17.625 * dewpoint_c / (243.04 + dewpoint_c)
        - 17.625 * temperature_c / (243.04 + temperature_c)
    )
    return np.clip(100.0 * np.exp(exponent), 0.0, 100.0)


def wet_bulb_temperature_stull(
    temperature_k: np.ndarray,
    dewpoint_k: np.ndarray,
) -> np.ndarray:
    """Estimate wet-bulb temperature in degrees Celsius after Stull (2011).

    The approximation uses air temperature and relative humidity at standard
    sea-level pressure. It has a reported mean absolute error below 0.3 degC
    for -20 to 50 degC and 5 to 99 percent relative humidity.
    """

    temperature_c = np.asarray(temperature_k, dtype=float) - 273.15
    relative_humidity = relative_humidity_from_temperature_and_dewpoint(
        temperature_k,
        dewpoint_k,
    )
    return (
        temperature_c
        * np.arctan(0.151977 * np.sqrt(relative_humidity + 8.313659))
        + np.arctan(temperature_c + relative_humidity)
        - np.arctan(relative_humidity - 1.676331)
        + 0.00391838
        * relative_humidity**1.5
        * np.arctan(0.023101 * relative_humidity)
        - 4.686035
    )


def shade_wbgt_proxy(
    temperature_k: np.ndarray,
    dewpoint_k: np.ndarray,
) -> np.ndarray:
    """Return a no-solar-load WBGT proxy in degrees Celsius.

    This uses psychrometric wet-bulb temperature in place of a measured
    natural wet-bulb temperature and assumes globe temperature equals air
    temperature. It is therefore a sensitivity metric, not full outdoor WBGT.
    """

    temperature_c = np.asarray(temperature_k, dtype=float) - 273.15
    wet_bulb_c = wet_bulb_temperature_stull(temperature_k, dewpoint_k)
    return 0.7 * wet_bulb_c + 0.3 * temperature_c


def humidex_from_temperature_and_dewpoint(
    temperature_k: np.ndarray,
    dewpoint_k: np.ndarray,
) -> np.ndarray:
    """Return Environment and Climate Change Canada's Humidex.

    Temperature and dewpoint must be in kelvin and broadcast to a common
    shape. Humidex is a dimensionless perceived-temperature index.
    """

    temperature_k = np.asarray(temperature_k, dtype=float)
    dewpoint_k = np.asarray(dewpoint_k, dtype=float)
    vapour_pressure_hpa = 6.11 * np.exp(
        5417.7530 * ((1.0 / 273.15) - (1.0 / dewpoint_k))
    )
    return temperature_k - 273.15 + 0.5555 * (vapour_pressure_hpa - 10.0)
