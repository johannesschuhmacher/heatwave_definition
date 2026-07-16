import importlib.util
import subprocess
import sys
import warnings
from pathlib import Path

import netCDF4 as nc
import numpy as np
import pandas as pd
import pytest

from heatwave_definition.hwmid import HWMID_METHOD_ID, _find_runs, calc_hwmid, canonical_day_of_year
from heatwave_definition.io import load_era5_t2m_daily_tmax
from heatwave_definition.metrics import load_metrics_npz
from heatwave_definition.plot_style import classify_top2_stability
from heatwave_definition.raw_copernicus import rank_daily_cells_by_hwmid
from heatwave_definition.regions import normalize_country_names
from heatwave_definition.ranking import (
    rank_years_by_cell_weighted_hwmid,
    rank_years_by_country_weighted_hwmid,
    rank_years_by_grid_metric,
)
from scripts.rank_cmip6_tas import Cmip6Group, format_year_ranges, missing_reference_years


def load_script_module(name: str):
    path = Path(__file__).resolve().parents[1] / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_normalize_country_names_splits_commas_and_semicolons():
    assert normalize_country_names(["Germany, France", "Spain; Italy"]) == [
        "Germany",
        "France",
        "Spain",
        "Italy",
    ]


def test_canonical_day_of_year_uses_hwmid_noleap_calendar():
    assert canonical_day_of_year(2, 28) == 59
    assert canonical_day_of_year(3, 1) == 60
    with pytest.raises(ValueError, match="29 February"):
        canonical_day_of_year(2, 29)


def test_cmip6_reference_preflight_includes_boundary_years():
    historical = Cmip6Group(
        institution="example",
        rcm="example-rcm",
        gcm="example-gcm",
        scenario="historical",
        variant="r1i1p1f1",
        version="v1",
        frequency="1hrPt",
        variable="tas",
        files=tuple(Path(f"tas_{year}.nc") for year in range(1981, 2011)),
    )

    missing = missing_reference_years(historical, (1981, 2010))

    assert missing == [1980, 2011]
    assert format_year_ranges(missing) == "1980,2011"


def test_load_metrics_npz_supports_raw_run_output(tmp_path):
    dates = pd.date_range("2000-01-01", "2001-12-31", freq="D")
    hwmid = np.ones((1, 2, 2))
    temp_anomaly = np.full((1, 2, 2), 2.0)
    heatwave_duration = np.full((1, 2, 2), 3.0)
    annual_tmax = np.full((1, 2, 2), 35.0)
    longitude = np.array([6.0, 7.0])
    latitude = np.array([48.0])
    path = tmp_path / "metrics_raw.npz"
    np.savez_compressed(
        path,
        hwmid=hwmid,
        hwmid_method=np.asarray(HWMID_METHOD_ID),
        temp_anomaly=temp_anomaly,
        heatwave_duration=heatwave_duration,
        annual_tmax=annual_tmax,
        longitude=longitude,
        latitude=latitude,
        dates=dates.astype("datetime64[ns]").astype("int64"),
    )

    data = load_metrics_npz(path)

    assert data.source_format == "npz"
    assert data.hwmid_method == HWMID_METHOD_ID
    np.testing.assert_array_equal(data.hwmid, hwmid)
    np.testing.assert_array_equal(data.temp_anomaly, temp_anomaly)
    np.testing.assert_array_equal(data.heatwave_duration, heatwave_duration)
    np.testing.assert_array_equal(data.annual_tmax, annual_tmax)
    np.testing.assert_array_equal(data.longitude, longitude)
    np.testing.assert_array_equal(data.latitude, latitude)
    assert data.dates.equals(dates)


def test_load_era5_t2m_directory_aggregates_hourly_to_daily_tmax(tmp_path):
    latitude = np.array([51.0, 50.0])
    longitude = np.array([7.0, 8.0])

    def write_era5_file(path: Path, start: str, base_celsius: float) -> None:
        hours = pd.date_range(start, periods=48, freq="h")
        seconds = (hours - pd.Timestamp("1970-01-01")) // pd.Timedelta(seconds=1)
        values = 273.15 + base_celsius + np.arange(48, dtype=np.float32)[:, None, None]
        values = values + np.zeros((48, len(latitude), len(longitude)), dtype=np.float32)

        with nc.Dataset(path, "w") as dataset:
            dataset.createDimension("valid_time", len(hours))
            dataset.createDimension("latitude", len(latitude))
            dataset.createDimension("longitude", len(longitude))
            time_var = dataset.createVariable("valid_time", "i8", ("valid_time",))
            time_var.units = "seconds since 1970-01-01"
            dataset.createVariable("latitude", "f4", ("latitude",))[:] = latitude
            dataset.createVariable("longitude", "f4", ("longitude",))[:] = longitude
            t2m = dataset.createVariable("t2m", "f4", ("valid_time", "latitude", "longitude"))
            t2m.units = "K"
            time_var[:] = seconds
            with warnings.catch_warnings():
                warnings.filterwarnings(
                    "ignore",
                    message="Setting the shape on a NumPy array has been deprecated",
                    category=DeprecationWarning,
                )
                t2m[:, :, :] = values

    write_era5_file(tmp_path / "t2m_era5_2001.nc", "2001-01-01", 10.0)
    write_era5_file(tmp_path / "t2m_era5_2000.nc", "2000-01-01", 20.0)

    data = load_era5_t2m_daily_tmax(tmp_path)

    assert list(data.dates.strftime("%Y-%m-%d")) == [
        "2000-01-01",
        "2000-01-02",
        "2001-01-01",
        "2001-01-02",
    ]
    np.testing.assert_array_equal(data.latitude, latitude)
    np.testing.assert_array_equal(data.longitude, longitude)
    assert np.isclose(float(data.max_daily_temp[0, 0, 0]), 43.0)
    assert np.isclose(float(data.max_daily_temp[1, 0, 0]), 67.0)
    assert np.isclose(float(data.max_daily_temp[2, 0, 0]), 33.0)


def test_calc_hwmid_detects_synthetic_heatwave():
    dates = pd.date_range("1980-01-01", "2012-12-31", freq="D")
    seasonal = 15.0 + 10.0 * np.sin(2.0 * np.pi * (dates.dayofyear.to_numpy() - 80) / 365.25)
    year_offsets = 0.05 * (dates.year.to_numpy() - 1980)
    values = seasonal.copy() + year_offsets
    event_mask = (dates >= "2011-07-10") & (dates <= "2011-07-15")
    values[event_mask] += 15.0

    tmax = values[:, None, None]
    result = calc_hwmid(
        tmax,
        latitude=np.array([50.0]),
        longitude=np.array([8.0]),
        datetime_vector=dates,
        ref_period=(1981, 2010),
    )

    years = np.array(sorted(dates.year.unique()))
    pos_2011 = int(np.where(years == 2011)[0][0])
    assert result[0][0, 0, pos_2011] > 0.0
    assert result[2][0, 0, pos_2011] >= 3.0
    assert result[3].shape == (1, 1, 365)


def test_calc_hwmid_matches_daily_magnitude_formula_and_minimum_duration():
    dates = pd.date_range("1980-01-01", "2012-12-31", freq="D")
    values = np.zeros(len(dates), dtype=float)
    for year, annual_maximum in zip(range(1981, 2011), range(10, 40)):
        values[dates == pd.Timestamp(year, 7, 1)] = annual_maximum

    values[(dates >= "2011-07-10") & (dates <= "2011-07-12")] = 50.0
    values[(dates >= "2012-07-10") & (dates <= "2012-07-11")] = 60.0

    result = calc_hwmid(
        values[:, None, None],
        latitude=np.array([50.0]),
        longitude=np.array([8.0]),
        datetime_vector=dates,
    )

    years = np.array(sorted(dates.year.unique()))
    pos_2011 = int(np.where(years == 2011)[0][0])
    pos_2012 = int(np.where(years == 2012)[0][0])
    t25 = np.quantile(np.arange(10.0, 40.0), 0.25)
    t75 = np.quantile(np.arange(10.0, 40.0), 0.75)
    expected = 3.0 * (50.0 - t25) / (t75 - t25)

    assert np.isclose(result[0][0, 0, pos_2011], expected)
    assert result[2][0, 0, pos_2011] == 3.0
    assert result[0][0, 0, pos_2012] == 0.0


def test_memory_aware_ranking_matches_full_grid_calculation():
    dates = pd.date_range("1980-01-01", "2012-12-31", freq="D")
    seasonal = 15.0 + 10.0 * np.sin(2.0 * np.pi * (dates.dayofyear.to_numpy() - 80) / 365.25)
    values = seasonal + 0.05 * (dates.year.to_numpy() - 1980)
    values[(dates >= "2011-07-10") & (dates <= "2011-07-15")] += 15.0
    values[(dates >= "2012-08-01") & (dates <= "2012-08-04")] += 12.0

    full = calc_hwmid(
        values[:, None, None],
        latitude=np.array([50.0]),
        longitude=np.array([8.0]),
        datetime_vector=dates,
    )
    ranking = rank_daily_cells_by_hwmid(values[:, None], dates, top_years=3)
    years = np.array(sorted(dates.year.unique()))
    expected_scores = full[0][0, 0, :]

    for row in ranking.itertuples(index=False):
        year_position = int(np.where(years == row.year)[0][0])
        assert np.isclose(row.hwmid_sum, expected_scores[year_position], rtol=1e-6)


def test_find_runs_splits_at_missing_calendar_days():
    dates = pd.DatetimeIndex(["2001-07-01", "2001-07-02", "2001-07-05", "2001-07-06", "2001-07-07"])
    assert _find_runs(np.ones(5, dtype=bool), 3, dates=dates) == [(2, 4)]


def test_calc_hwmid_rejects_incomplete_reference_year():
    dates = pd.date_range("1980-01-01", "2012-12-31", freq="D")
    keep = dates != pd.Timestamp("1995-07-01")
    with pytest.raises(ValueError, match="Reference year 1995 is incomplete"):
        calc_hwmid(
            np.zeros((int(keep.sum()), 1, 1)),
            latitude=np.array([50.0]),
            longitude=np.array([8.0]),
            datetime_vector=dates[keep],
        )


def test_rank_years_by_country_weighted_hwmid_distributes_country_weights():
    import heatwave_definition.ranking as ranking_module

    latitude = np.array([50.0, 51.0])
    longitude = np.array([7.0, 8.0])
    dates = pd.date_range("2000-01-01", "2001-12-31", freq="D")
    hwmid = np.array(
        [
            [[10.0, 0.0], [0.0, 0.0]],
            [[0.0, 4.0], [0.0, 4.0]],
        ]
    )

    original_classifier = ranking_module.classify_countries_matrix

    def fake_classifier(_latitude, _longitude, countries):
        country = list(countries)[0]
        mask = np.zeros((2, 2), dtype=bool)
        if country == "CountryA":
            mask[0, 0] = True
        elif country == "CountryB":
            mask[1, 0] = True
            mask[1, 1] = True
        else:
            raise AssertionError(country)
        return mask

    try:
        ranking_module.classify_countries_matrix = fake_classifier
        result = rank_years_by_country_weighted_hwmid(
            latitude,
            longitude,
            hwmid,
            dates,
            {"CountryA": 1.0, "CountryB": 3.0},
            no_years=2,
        )
    finally:
        ranking_module.classify_countries_matrix = original_classifier

    assert result.loc[0, "year"] == 2001
    assert result.loc[1, "year"] == 2000
    assert result.loc[0, "weighted_hwmid"] > result.loc[1, "weighted_hwmid"]


def test_rank_years_by_grid_metric_supports_area_weighted_mean():
    import heatwave_definition.ranking as ranking_module

    latitude = np.array([0.0, 60.0])
    longitude = np.array([7.0])
    dates = pd.date_range("2000-01-01", "2001-12-31", freq="D")
    metric = np.array([[[1.0, 1.0]], [[0.0, 3.0]]])
    original_classifier = ranking_module.classify_countries_matrix

    try:
        ranking_module.classify_countries_matrix = lambda *_args, **_kwargs: np.ones((2, 1), dtype=bool)
        result = rank_years_by_grid_metric(
            latitude,
            longitude,
            metric,
            dates,
            countries=["Synthetic"],
            aggregation="area_weighted_mean",
            no_years=2,
        )
    finally:
        ranking_module.classify_countries_matrix = original_classifier

    assert result.loc[0, "year"] == 2001
    assert np.isclose(result.loc[0, "score"], (1.0 + 0.5 * 3.0) / 1.5)


def test_rank_years_by_cell_weighted_hwmid_uses_explicit_weights():
    dates = pd.date_range("2000-01-01", "2001-12-31", freq="D")
    hwmid = np.array(
        [
            [[10.0, 0.0], [0.0, 0.0]],
            [[0.0, 0.0], [0.0, 4.0]],
        ]
    )
    weights = np.array([[0.1, 0.0], [0.0, 0.9]])

    result = rank_years_by_cell_weighted_hwmid(hwmid, dates, weights, no_years=2)

    assert result.loc[0, "year"] == 2001
    assert np.isclose(result.loc[0, "weighted_hwmid"], 3.6)
    assert np.isclose(result.loc[1, "weighted_hwmid"], 1.0)


def test_tyndp2024_pemmdb_weight_helpers_map_nodes_and_aggregate_components():
    module = load_script_module("derive_country_weights_from_tyndp2024_pemmdb")

    assert module.map_node_to_country("DE00") == "Germany"
    assert module.map_node_to_country("FR15") == "France"
    assert module.map_node_to_country("ITCN") == "Italy"
    assert module.map_node_to_country("NO00") is None

    result = module.aggregate_components(
        {
            "thermal": 10.0,
            "other_non_res": 2.0,
            "nuclear": 3.0,
            "wind_onshore": 4.0,
            "wind_offshore": 5.0,
            "solar_pv": 6.0,
            "solar_rooftop": 7.0,
            "solar_csp": 8.0,
            "hydro": 9.0,
            "pumped_hydro": 12.0,
            "other_res": 1.0,
            "bio": 0.5,
            "storage": 11.0,
        }
    )

    assert result["wind"] == 9.0
    assert result["pv"] == 13.0
    assert result["solar"] == 21.0
    assert result["renewables"] == 40.0
    assert result["pumped_hydro"] == 12.0
    assert result["storage_total"] == 23.0
    assert result["thermal"] == 12.0
    assert result["thermal_nuclear"] == 15.0
    assert result["capacity"] == 78.0


def test_top2_stability_classification_matches_figure_legend():
    reference = (2043, 2070)

    assert classify_top2_stability(reference, (2043, 2070)).key == "match_both"
    assert classify_top2_stability(reference, (2043, 2041)).key == "rank1_match"
    assert classify_top2_stability(reference, (2070, 2043)).key == "rank1_changes_reference_retained"
    assert classify_top2_stability(reference, (2041, 2039)).key == "no_reference_top2"


def test_demo_ranks_injected_events_first(tmp_path):
    repo = Path(__file__).resolve().parents[1]
    output = tmp_path / "demo.csv"
    subprocess.run(
        [sys.executable, str(repo / "scripts" / "run_demo.py"), "--output", str(output)],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )

    ranking = pd.read_csv(output)
    assert ranking.loc[:1, "year"].tolist() == [2011, 2012]
    assert ranking.loc[0, "hwmid_sum"] > ranking.loc[1, "hwmid_sum"] > 0


def test_complete_workflow_exposes_required_input_options():
    repo = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [sys.executable, str(repo / "scripts" / "run_complete_climate_workflow.py"), "--help"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )

    assert "--eobs-file" in result.stdout
    assert "--cmip6-root" in result.stdout
