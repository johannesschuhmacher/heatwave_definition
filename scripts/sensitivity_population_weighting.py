"""Run historical population-weighted HWMId sensitivity rankings.

The script uses WorldPop 1 km UN-adjusted population counts for Germany and
France and aggregates them to the HWMId grid. The resulting grid-cell
population counts are used as weights for a population-weighted mean HWMId.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import urllib.request
import zipfile

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from heatwave_definition.metrics import load_metrics_file, resolve_metrics_file
from heatwave_definition.plot_style import (
    ANNOTATION_SIZE,
    DATASET_DISPLAY,
    DATASET_ORDER,
    LEGEND_SIZE,
    PANEL_TITLE_SIZE,
    STABILITY_CMAP,
    STABILITY_NORM,
    apply_manuscript_style,
    classify_top2_stability,
    stability_legend_handles,
)
from heatwave_definition.ranking import rank_years_by_cell_weighted_hwmid, rank_years_by_hwmid


REPO = Path(__file__).resolve().parents[1]
DEFAULT_CACHE_DIR = REPO / "data" / "worldpop"
DEFAULT_OUTPUT_DIR = REPO / "outputs" / "sensitivity"
DEFAULT_FIGURE_DIR = REPO / "outputs" / "figures"
DEFAULT_WORLPOP_ALIAS = "wpicuadj1km"
WORLPOP_API = "https://www.worldpop.org/rest/data/pop/{alias}?iso3={iso3}"

DATASETS = [
    ("Historical / E-OBS", ["metrics_e_obs.npz"]),
]

COUNTRY_ISO3 = {
    "Germany": "DEU",
    "France": "FRA",
}


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    apply_manuscript_style()
    args.cache_dir.mkdir(parents=True, exist_ok=True)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    args.figure_dir.mkdir(parents=True, exist_ok=True)

    country_records = [
        resolve_worldpop_record(country, COUNTRY_ISO3[country], args.population_year, args.worldpop_alias, args.cache_dir)
        for country in args.countries
    ]

    ranking_rows = []
    diagnostic_rows = []
    for dataset, filenames in DATASETS:
        data = load_metrics_file(resolve_metrics_file(args.metrics_dir, filenames))

        baseline = rank_years_by_hwmid(
            data.latitude,
            data.longitude,
            data.hwmid,
            data.dates,
            no_years=args.top_years,
            countries=args.countries,
        )
        baseline = baseline.rename(columns={"hwmid_sum": "score"})
        baseline.insert(0, "dataset", dataset)
        baseline.insert(1, "criterion", "unweighted_hwmid_sum")
        baseline.insert(2, "criterion_label", "Unweighted HWMId sum")
        baseline["score_type"] = "hwmid_sum"
        baseline["hwmid_method"] = data.hwmid_method
        ranking_rows.append(baseline)

        population_weights, diagnostics = build_population_weights(
            data.latitude,
            data.longitude,
            country_records,
            chunksize=args.chunksize,
        )
        diagnostic_rows.extend(
            {"dataset": dataset, **row}
            for row in diagnostics
        )

        population = rank_years_by_cell_weighted_hwmid(
            data.hwmid,
            data.dates,
            population_weights,
            no_years=args.top_years,
            score_column="score",
        )
        population.insert(0, "dataset", dataset)
        population.insert(1, "criterion", "population_weighted_hwmid_mean")
        population.insert(2, "criterion_label", "Population-weighted HWMId mean")
        population["score_type"] = "population_weighted_hwmid_mean"
        population["hwmid_method"] = data.hwmid_method
        ranking_rows.append(population)

    rankings = pd.concat(ranking_rows, ignore_index=True)
    rankings["population_year"] = args.population_year
    rankings["population_source"] = "WorldPop 1 km UN-adjusted population counts"
    rankings["population_source_alias"] = args.worldpop_alias

    full_path = args.output_dir / "population_weighting_top_years.csv"
    rankings.to_csv(full_path, index=False)

    top2 = rankings[rankings["rank"] <= 2].copy()
    summary_path = args.output_dir / "population_weighting_top2_summary.csv"
    top2.to_csv(summary_path, index=False)

    diagnostics = pd.DataFrame(diagnostic_rows)
    diagnostics_path = args.output_dir / "population_weighting_diagnostics.csv"
    diagnostics.to_csv(diagnostics_path, index=False)

    figure_path = args.figure_dir / "population_weighting_top2_heatmap.png"
    plot_top2_heatmap(top2, figure_path)

    print(full_path)
    print(summary_path)
    print(diagnostics_path)
    print(figure_path)


def resolve_worldpop_record(country: str, iso3: str, year: int, alias: str, cache_dir: Path) -> dict:
    url = WORLPOP_API.format(alias=alias, iso3=iso3)
    with urllib.request.urlopen(url, timeout=60) as response:
        payload = json.load(response)

    records = [record for record in payload.get("data", []) if str(record.get("popyear")) == str(year)]
    if not records:
        raise ValueError(f"No WorldPop record for {iso3} {year} in {alias}")
    record = records[0]
    zip_urls = [item for item in record.get("files", []) if str(item).lower().endswith(".zip")]
    if not zip_urls:
        raise ValueError(f"WorldPop record for {iso3} {year} has no ASCII XYZ zip file")

    source_url = zip_urls[0]
    local_path = cache_dir / source_url.rsplit("/", 1)[-1]
    if not local_path.exists():
        urllib.request.urlretrieve(source_url, local_path)

    return {
        "country": country,
        "iso3": iso3,
        "year": year,
        "alias": alias,
        "path": local_path,
        "source_url": source_url,
        "title": record.get("title", ""),
        "doi": record.get("doi", ""),
        "license": record.get("license", ""),
        "url_summary": record.get("url_summary", ""),
    }


def build_population_weights(
    latitude: np.ndarray,
    longitude: np.ndarray,
    records: list[dict],
    chunksize: int,
) -> tuple[np.ndarray, list[dict]]:
    lat_edges = centers_to_edges(np.asarray(latitude, dtype=float))
    lon_edges = centers_to_edges(np.asarray(longitude, dtype=float))
    weights = np.zeros((len(latitude), len(longitude)), dtype=float)
    diagnostics = []

    for record in records:
        country_weights = np.zeros_like(weights)
        source_population = 0.0
        positive_pixels = 0
        assigned_population = 0.0
        assigned_pixels = 0

        for chunk in read_worldpop_xyz_chunks(record["path"], chunksize=chunksize):
            lon = chunk["X"].to_numpy(dtype=float)
            lat = chunk["Y"].to_numpy(dtype=float)
            pop = chunk["Z"].to_numpy(dtype=float)
            valid = np.isfinite(lon) & np.isfinite(lat) & np.isfinite(pop) & (pop > 0)
            source_population += float(np.nansum(np.where(valid, pop, 0.0)))
            positive_pixels += int(np.count_nonzero(valid))

            lon_idx = np.searchsorted(lon_edges, lon, side="right") - 1
            lat_idx = np.searchsorted(lat_edges, lat, side="right") - 1
            inside = (
                valid
                & (lon_idx >= 0)
                & (lon_idx < len(longitude))
                & (lat_idx >= 0)
                & (lat_idx < len(latitude))
            )
            if not np.any(inside):
                continue

            assigned_population += float(np.nansum(pop[inside]))
            assigned_pixels += int(np.count_nonzero(inside))
            np.add.at(country_weights, (lat_idx[inside], lon_idx[inside]), pop[inside])

        weights += country_weights
        diagnostics.append(
            {
                "country": record["country"],
                "iso3": record["iso3"],
                "population_year": record["year"],
                "source_population": source_population,
                "assigned_population": assigned_population,
                "assigned_population_share": assigned_population / source_population if source_population else np.nan,
                "positive_worldpop_pixels": positive_pixels,
                "assigned_worldpop_pixels": assigned_pixels,
                "weighted_hwmid_cells": int(np.count_nonzero(country_weights > 0)),
                "worldpop_doi": record["doi"],
                "worldpop_license": record["license"],
                "worldpop_url": record["source_url"],
            }
        )

    return weights, diagnostics


def read_worldpop_xyz_chunks(path: Path, chunksize: int):
    with zipfile.ZipFile(path) as archive:
        members = [name for name in archive.namelist() if name.lower().endswith(".csv")]
        if len(members) != 1:
            raise ValueError(f"Expected one CSV member in {path}, found {members}")
        with archive.open(members[0]) as handle:
            yield from pd.read_csv(handle, chunksize=chunksize)


def centers_to_edges(centers: np.ndarray) -> np.ndarray:
    if centers.ndim != 1 or len(centers) < 2:
        raise ValueError("Grid centers must be a one-dimensional array with at least two values")
    if not np.all(np.diff(centers) > 0):
        raise ValueError("Grid centers must be strictly increasing")
    midpoints = (centers[:-1] + centers[1:]) / 2.0
    first = centers[0] - (midpoints[0] - centers[0])
    last = centers[-1] + (centers[-1] - midpoints[-1])
    return np.concatenate([[first], midpoints, [last]])


def plot_top2_heatmap(top2: pd.DataFrame, output: Path) -> None:
    dataset_order = [dataset for dataset in DATASET_ORDER if dataset in set(top2["dataset"])]
    values = np.zeros((1, len(dataset_order)), dtype=int)
    labels = np.empty(values.shape, dtype=object)
    text_colors = np.empty(values.shape, dtype=object)

    for column, dataset in enumerate(dataset_order):
        group = top2[top2["dataset"] == dataset]
        reference = top2_tuple(group, "unweighted_hwmid_sum")
        candidate = top2_tuple(group, "population_weighted_hwmid_mean")
        category = classify_top2_stability(reference, candidate)
        values[0, column] = category.code
        labels[0, column] = f"{candidate[0]}\n({candidate[1]})"
        text_colors[0, column] = category.text_color

    fig, ax = plt.subplots(figsize=(7.2, 2.2), constrained_layout=True)
    ax.imshow(values, cmap=STABILITY_CMAP, norm=STABILITY_NORM, aspect="auto")
    ax.set_xticks(np.arange(len(dataset_order)), [DATASET_DISPLAY.get(dataset, dataset) for dataset in dataset_order])
    ax.set_yticks([0], ["Population-\nweighted mean"])
    ax.set_title("Population-weighted heatwave-year sensitivity", fontsize=PANEL_TITLE_SIZE)
    ax.tick_params(length=0)

    for row in range(values.shape[0]):
        for column in range(values.shape[1]):
            ax.text(
                column,
                row,
                labels[row, column],
                ha="center",
                va="center",
                fontsize=ANNOTATION_SIZE,
                fontweight="bold",
                color=text_colors[row, column],
            )

    ax.legend(
        handles=stability_legend_handles(),
        frameon=False,
        loc="upper center",
        bbox_to_anchor=(0.5, -0.35),
        ncol=2,
        fontsize=LEGEND_SIZE,
    )
    fig.savefig(output, dpi=220)
    plt.close(fig)


def top2_tuple(top2: pd.DataFrame, criterion: str) -> tuple[int, int]:
    subset = top2[top2["criterion"] == criterion].sort_values("rank")
    if len(subset) < 2:
        raise ValueError(f"Need at least two ranked years for criterion {criterion!r}")
    return int(subset.iloc[0]["year"]), int(subset.iloc[1]["year"])


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--metrics-dir", type=Path, default=REPO)
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--figure-dir", type=Path, default=DEFAULT_FIGURE_DIR)
    parser.add_argument("--countries", nargs="+", default=["Germany", "France"], choices=sorted(COUNTRY_ISO3))
    parser.add_argument("--population-year", type=int, default=2020)
    parser.add_argument("--worldpop-alias", default=DEFAULT_WORLPOP_ALIAS)
    parser.add_argument("--top-years", type=int, default=10)
    parser.add_argument("--chunksize", type=int, default=500_000)
    return parser.parse_args(argv)


if __name__ == "__main__":
    main()
