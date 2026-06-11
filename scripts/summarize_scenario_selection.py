"""Create the compact scenario-selection table used by the working paper."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


REPO = Path(__file__).resolve().parents[1]
DEFAULT_INPUT_DIR = REPO / "outputs" / "ranking_from_config"
DEFAULT_OUTPUT = DEFAULT_INPUT_DIR / "scenario_selection_summary.csv"

RANKINGS = [
    ("Historical / E-OBS", "ranked_years_e_obs_from_metrics.csv"),
    ("RCP4.5 / IPSL-WRF", "ranked_years_copernicus_rcp45_from_metrics.csv"),
    ("RCP8.5 / MPI-CLM", "ranked_years_copernicus_rcp85_from_metrics.csv"),
]


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    records = []

    for dataset, filename in RANKINGS:
        path = args.input_dir / filename
        ranking = pd.read_csv(path).head(args.top_years)
        for _, row in ranking.iterrows():
            records.append(
                {
                    "dataset": dataset,
                    "rank": int(row["rank"]),
                    "year": int(row["year"]),
                    "hwmid_sum_de_fr": float(row["hwmid_sum"]),
                    "country_cells": int(row["country_cells"]),
                    "source": filename,
                }
            )

    summary = pd.DataFrame.from_records(records)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    summary.to_csv(args.output, index=False)
    print(args.output)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=DEFAULT_INPUT_DIR,
        help="Directory containing ranked_years_*.csv files.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Output summary CSV path.",
    )
    parser.add_argument(
        "--top-years",
        type=int,
        default=2,
        help="Number of leading years per dataset to include.",
    )
    return parser.parse_args(argv)


if __name__ == "__main__":
    main()
