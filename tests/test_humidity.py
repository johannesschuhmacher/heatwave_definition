import numpy as np

from heatwave_definition.humidity import (
    humidex_from_temperature_and_dewpoint,
    relative_humidity_from_temperature_and_dewpoint,
    shade_wbgt_proxy,
    wet_bulb_temperature_stull,
)


def test_humidex_matches_environment_canada_formula() -> None:
    result = humidex_from_temperature_and_dewpoint(
        np.array([303.15]),
        np.array([293.15]),
    )

    np.testing.assert_allclose(result, [37.57], atol=0.02)


def test_relative_humidity_is_saturated_at_the_dewpoint() -> None:
    result = relative_humidity_from_temperature_and_dewpoint(
        np.array([303.15]),
        np.array([303.15]),
    )

    np.testing.assert_allclose(result, [100.0])


def test_wet_bulb_and_shade_wbgt_are_bounded_by_dewpoint_and_temperature() -> None:
    temperature = np.array([303.15])
    dewpoint = np.array([293.15])

    wet_bulb = wet_bulb_temperature_stull(temperature, dewpoint)
    wbgt = shade_wbgt_proxy(temperature, dewpoint)

    assert 20.0 < wet_bulb[0] < 30.0
    np.testing.assert_allclose(wbgt, 0.7 * wet_bulb + 0.3 * 30.0)
