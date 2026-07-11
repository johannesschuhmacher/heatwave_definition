"""Run country-set and top-N sensitivity rankings from metric arrays."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from heatwave_definition.metrics import load_metrics_file, resolve_metrics_file
from heatwave_definition.ranking import rank_years_by_hwmid


REPO = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = REPO / "outputs" / "sensitivity"

DATASETS = [
    ("Historical / E-OBS", ["metrics_e_obs.npz", "metrics_e_obs.pkl"]),
    ("RCP4.5 / IPSL-WRF", ["metrics_copernicus_rcp45.npz", "metrics_copernicus_45.pkl"]),
    ("RCP8.5 / MPI-CLM", ["metrics_copernicus_rcp85.npz", "metrics_copernicus_85.pkl"]),
]

WESTERN_CENTRAL_EUROPE = [
    "Germany",
    "France",
    "Belgium",
    "Netherlands",
    "Luxembourg",
    "Switzerland",
    "Austria",
    "Italy",
    "Spain",
    "Poland",
    "Czechia",
]

COUNTRY_CODES = {
    "Germany": "DE",
    "France": "FR",
    "Belgium": "BE",
    "Netherlands": "NL",
    "Luxembourg": "LU",
    "Switzerland": "CH",
    "Austria": "AT",
    "Italy": "IT",
    "Spain": "ES",
    "Poland": "PL",
    "Czechia": "CZ",
}

BASE_COUNTRY_SETS = {
    "DE_FR": ["Germany", "France"],
    "DE_only": ["Germany"],
    "FR_only": ["France"],
    "DE_FR_Benelux_Alps": [
        "Germany",
        "France",
        "Belgium",
        "Netherlands",
        "Luxembourg",
        "Switzerland",
        "Austria",
    ],
    "Western_Central_Europe": WESTERN_CENTRAL_EUROPE,
}

COUNTRY_SETS = {
    **BASE_COUNTRY_SETS,
    **{
        f"WCE_minus_{COUNTRY_CODES[country]}": [
            member for member in WESTERN_CENTRAL_EUROPE if member != country
        ]
        for country in WESTERN_CENTRAL_EUROPE
    },
}


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    rows = []
    for dataset, filenames in DATASETS:
        data = load_metrics_file(resolve_metrics_file(args.repo, filenames))
        for set_name, countries in COUNTRY_SETS.items():
            ranking = rank_years_by_hwmid(
                data.latitude,
                data.longitude,
                data.hwmid,
                data.dates,
                no_years=args.top_years,
                countries=countries,
            )
            ranking.insert(0, "dataset", dataset)
            ranking.insert(1, "country_set", set_name)
            ranking.insert(2, "countries", "+".join(countries))
            rows.append(ranking)

    result = pd.concat(rows, ignore_index=True)
    full_path = args.output_dir / "country_set_top_years.csv"
    result.to_csv(full_path, index=False)

    top2 = result[result["rank"] <= 2].copy()
    summary_path = args.output_dir / "country_set_top2_summary.csv"
    top2.to_csv(summary_path, index=False)

    print(full_path)
    print(summary_path)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=REPO)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--top-years", type=int, default=10)
    return parser.parse_args(argv)


if __name__ == "__main__":
    main()
