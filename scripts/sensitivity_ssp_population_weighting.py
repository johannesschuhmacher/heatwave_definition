"""Rank primary future climate runs with fixed-year SSP population weights."""

from __future__ import annotations

import argparse
from pathlib import Path
import re

import matplotlib.pyplot as plt
import netCDF4 as nc
import numpy as np
import pandas as pd

from heatwave_definition.plot_style import (
    STABILITY_CMAP,
    STABILITY_NORM,
    apply_manuscript_style,
    classify_top2_stability,
    save_manuscript_figure,
    stability_legend_handles,
)
from heatwave_definition.regions import classify_countries_matrix


REPO = Path(__file__).resolve().parents[1]
DEFAULT_METRICS_DIR = REPO / "outputs" / "cmip5_current"
DEFAULT_OUTPUT_DIR = REPO / "outputs" / "reviewer_revision" / "ssp_population"
DEFAULT_FIGURE_DIR = REPO / "outputs" / "reviewer_revision" / "figures"
SSP_SOURCE = "ISIMIP2b secondary population input data (v1.0)"
SSP_DOI = "https://doi.org/10.48364/ISIMIP.432399"
EARTH_RADIUS_M = 6_371_000.0

RUNS = [
    ("RCP4.5 / IPSL-WRF", "cmip5_rcp45_ipsl_wrf_wce_cell_metrics.npz"),
    ("RCP8.5 / MPI-CLM", "cmip5_rcp85_mpi_clm_wce_cell_metrics.npz"),
]


def main() -> None:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    args.figure_dir.mkdir(parents=True, exist_ok=True)

    grid_lat, grid_lon = read_grid(args.grid_file)
    target_lat, target_lon, grid_spacing = selected_cell_coordinates(grid_lat, grid_lon)
    population_weights = {
        f"SSP{ssp}": population_weights_for_cells(
            args.population_dir / f"population_ssp{ssp}soc_0p5deg_annual_2006-2100.nc4",
            args.population_year,
            target_lat,
            target_lon,
            grid_spacing,
        )
        for ssp in range(1, 6)
    }

    rows = []
    diagnostics = []
    for dataset, filename in RUNS:
        metrics = np.load(args.metrics_dir / filename)
        cell_lat = np.asarray(metrics["cell_lat"], dtype=float)
        cell_lon = np.asarray(metrics["cell_lon"], dtype=float) if "cell_lon" in metrics else target_lon
        if not np.array_equal(cell_lat, target_lat) or not np.array_equal(cell_lon, target_lon):
            raise ValueError(f"Grid coordinates do not match cached metrics for {dataset}")

        country_mask = np.asarray(metrics["country_Germany"], dtype=bool) | np.asarray(
            metrics["country_France"], dtype=bool
        )
        hwmid = np.asarray(metrics["hwmid"], dtype=float)
        years = np.asarray(metrics["years"], dtype=int)

        baseline_scores = np.nansum(hwmid[country_mask, :], axis=0)
        rows.append(ranked_rows(dataset, "Unweighted", baseline_scores, years, args.top_years))

        for weighting, weights in population_weights.items():
            selected_weights = np.where(country_mask, weights, 0.0)
            selected_weights /= np.nansum(selected_weights)
            scores = np.nansum(hwmid * selected_weights[:, None], axis=0)
            rows.append(ranked_rows(dataset, weighting, scores, years, args.top_years))
            diagnostics.append(
                {
                    "dataset": dataset,
                    "weighting": weighting,
                    "population_year": args.population_year,
                    "positive_weight_cells": int(np.count_nonzero(selected_weights > 0)),
                    "weight_sum": float(np.nansum(selected_weights)),
                }
            )

    rankings = pd.concat(rows, ignore_index=True)
    rankings["population_year"] = args.population_year
    rankings["population_source"] = SSP_SOURCE
    rankings["population_source_doi"] = SSP_DOI
    rankings_path = args.output_dir / "ssp_population_weighting_top_years.csv"
    rankings.to_csv(rankings_path, index=False)

    top2 = rankings[rankings["rank"] <= 2].copy()
    top2_path = args.output_dir / "ssp_population_weighting_top2_summary.csv"
    top2.to_csv(top2_path, index=False)
    pd.DataFrame(diagnostics).to_csv(args.output_dir / "ssp_population_weighting_diagnostics.csv", index=False)

    figure_path = args.figure_dir / "ssp_population_weighting_top2_heatmap.png"
    plot_top2(top2, figure_path, args.population_year)
    print(rankings_path)
    print(top2_path)
    print(figure_path)


def read_grid(path: Path) -> tuple[np.ndarray, np.ndarray]:
    with nc.Dataset(path) as dataset:
        return np.asarray(dataset.variables["lat"][:], dtype=float), np.asarray(
            dataset.variables["lon"][:], dtype=float
        )


def selected_cell_coordinates(
    latitude: np.ndarray, longitude: np.ndarray
) -> tuple[np.ndarray, np.ndarray, tuple[float, float]]:
    countries = [
        "Germany", "France", "Belgium", "Netherlands", "Luxembourg", "Switzerland",
        "Austria", "Italy", "Spain", "Poland", "Czechia",
    ]
    mask = classify_countries_matrix(latitude, longitude, countries)
    lon_grid, lat_grid = np.meshgrid(longitude, latitude)
    return lat_grid[mask], lon_grid[mask], (float(np.median(np.diff(latitude))), float(np.median(np.diff(longitude))))


def population_weights_for_cells(
    path: Path,
    year: int,
    target_lat: np.ndarray,
    target_lon: np.ndarray,
    target_spacing: tuple[float, float],
) -> np.ndarray:
    if not path.exists():
        raise FileNotFoundError(path)
    with nc.Dataset(path) as dataset:
        time = dataset.variables["time"]
        years = decode_years(np.asarray(time[:], dtype=float), time.units)
        matches = np.where(years == year)[0]
        if len(matches) != 1:
            raise ValueError(f"Year {year} not found exactly once in {path}")
        source_lat = np.asarray(dataset.variables["lat"][:], dtype=float)
        source_lon = np.asarray(dataset.variables["lon"][:], dtype=float)
        population = np.ma.filled(
            dataset.variables["number_of_people"][int(matches[0]), :, :],
            np.nan,
        ).astype(float)
        if source_lat[0] > source_lat[-1]:
            source_lat = source_lat[::-1]
            population = population[::-1, :]
        source_area = regular_grid_cell_area(source_lat, float(np.median(np.diff(source_lon))))
        density = population / source_area[:, None]
        interpolated_density = bilinear_regular_grid(
            source_lat,
            source_lon,
            np.nan_to_num(density, nan=0.0),
            target_lat,
            target_lon,
        )

    target_area = cell_area(target_lat, abs(target_spacing[0]), abs(target_spacing[1]))
    weights = np.where(np.isfinite(interpolated_density) & (interpolated_density > 0), interpolated_density * target_area, 0.0)
    if np.nansum(weights) <= 0:
        raise ValueError(f"No positive population weights derived from {path}")
    return weights


def decode_years(values: np.ndarray, units: str) -> np.ndarray:
    match = re.search(r"years since\s+(\d{4})", units)
    if not match:
        raise ValueError(f"Unsupported population time units: {units!r}")
    return np.rint(values + int(match.group(1))).astype(int)


def bilinear_regular_grid(
    source_lat: np.ndarray,
    source_lon: np.ndarray,
    values: np.ndarray,
    target_lat: np.ndarray,
    target_lon: np.ndarray,
) -> np.ndarray:
    lat_upper = np.searchsorted(source_lat, target_lat, side="right")
    lon_upper = np.searchsorted(source_lon, target_lon, side="right")
    lat_upper = np.clip(lat_upper, 1, len(source_lat) - 1)
    lon_upper = np.clip(lon_upper, 1, len(source_lon) - 1)
    lat_lower = lat_upper - 1
    lon_lower = lon_upper - 1

    lat_fraction = (target_lat - source_lat[lat_lower]) / (source_lat[lat_upper] - source_lat[lat_lower])
    lon_fraction = (target_lon - source_lon[lon_lower]) / (source_lon[lon_upper] - source_lon[lon_lower])
    lower = values[lat_lower, lon_lower] * (1.0 - lon_fraction) + values[lat_lower, lon_upper] * lon_fraction
    upper = values[lat_upper, lon_lower] * (1.0 - lon_fraction) + values[lat_upper, lon_upper] * lon_fraction
    return lower * (1.0 - lat_fraction) + upper * lat_fraction


def regular_grid_cell_area(latitude: np.ndarray, lon_spacing_deg: float) -> np.ndarray:
    lat_spacing_deg = float(np.median(np.diff(latitude)))
    return cell_area(latitude, abs(lat_spacing_deg), abs(lon_spacing_deg))


def cell_area(latitude: np.ndarray, lat_spacing_deg: float, lon_spacing_deg: float) -> np.ndarray:
    south = np.deg2rad(latitude - lat_spacing_deg / 2.0)
    north = np.deg2rad(latitude + lat_spacing_deg / 2.0)
    lon_width = np.deg2rad(lon_spacing_deg)
    return EARTH_RADIUS_M**2 * lon_width * (np.sin(north) - np.sin(south))


def ranked_rows(dataset: str, weighting: str, scores: np.ndarray, years: np.ndarray, top_years: int) -> pd.DataFrame:
    order = np.argsort(np.where(np.isfinite(scores), scores, -np.inf))[::-1][:top_years]
    return pd.DataFrame(
        {
            "dataset": dataset,
            "weighting": weighting,
            "rank": np.arange(1, len(order) + 1),
            "year": years[order],
            "score": scores[order],
        }
    )


def plot_top2(top2: pd.DataFrame, output: Path, population_year: int) -> None:
    apply_manuscript_style()
    datasets = [dataset for dataset, _ in RUNS]
    weightings = ["SSP1", "SSP2", "SSP3", "SSP4", "SSP5"]
    values = np.zeros((len(weightings), len(datasets)), dtype=int)
    labels = np.empty(values.shape, dtype=object)
    colors = np.empty(values.shape, dtype=object)

    for column, dataset in enumerate(datasets):
        reference = top2_tuple(top2, dataset, "Unweighted")
        for row, weighting in enumerate(weightings):
            candidate = top2_tuple(top2, dataset, weighting)
            category = classify_top2_stability(reference, candidate)
            values[row, column] = category.code
            labels[row, column] = f"{candidate[0]}\n({candidate[1]})"
            colors[row, column] = category.text_color

    fig, ax = plt.subplots(figsize=(6.8, 4.2), constrained_layout=True)
    ax.imshow(values, cmap=STABILITY_CMAP, norm=STABILITY_NORM, aspect="auto")
    ax.set_xticks(range(len(datasets)), ["RCP4.5\nIPSL-WRF", "RCP8.5\nMPI-CLM"])
    ax.set_yticks(range(len(weightings)), [f"{name} population" for name in weightings])
    ax.tick_params(length=0)
    ax.set_title(f"Fixed-{population_year} SSP population-weighting sensitivity")
    for row in range(values.shape[0]):
        for column in range(values.shape[1]):
            ax.text(column, row, labels[row, column], ha="center", va="center", color=colors[row, column], fontweight="bold")
    ax.legend(handles=stability_legend_handles(), frameon=False, loc="upper center", bbox_to_anchor=(0.5, -0.12), ncol=2)
    save_manuscript_figure(fig, output)
    plt.close(fig)


def top2_tuple(top2: pd.DataFrame, dataset: str, weighting: str) -> tuple[int, int]:
    subset = top2[(top2["dataset"] == dataset) & (top2["weighting"] == weighting)].sort_values("rank")
    return int(subset.iloc[0]["year"]), int(subset.iloc[1]["year"])


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--metrics-dir", type=Path, default=DEFAULT_METRICS_DIR)
    parser.add_argument("--population-dir", type=Path, required=True)
    parser.add_argument("--grid-file", type=Path, required=True)
    parser.add_argument("--population-year", type=int, default=2040)
    parser.add_argument("--top-years", type=int, default=10)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--figure-dir", type=Path, default=DEFAULT_FIGURE_DIR)
    return parser.parse_args()


if __name__ == "__main__":
    main()
