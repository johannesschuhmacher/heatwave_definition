"""Create the compact scenario-selection table used by the manuscript."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


REPO = Path(__file__).resolve().parents[1]
DEFAULT_INPUT_DIR = REPO / "outputs" / "ranking_from_config"
DEFAULT_OUTPUT = DEFAULT_INPUT_DIR / "scenario_selection_summary.csv"

RANKINGS = [
    ("Historical / E-OBS", ["ranked_years_e_obs.csv"]),
    ("Historical / ERA5", ["ranked_years_era5.csv"]),
    ("RCP4.5 / IPSL-WRF", ["ranked_years_copernicus_rcp45.csv"]),
    ("RCP8.5 / MPI-CLM", ["ranked_years_copernicus_rcp85.csv"]),
]


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    records = []

    for dataset, filenames in RANKINGS:
        path = resolve_input(args.input_dir, filenames)
        ranking = pd.read_csv(path).head(args.top_years)
        for _, row in ranking.iterrows():
            records.append(
                {
                    "dataset": dataset,
                    "rank": int(row["rank"]),
                    "year": int(row["year"]),
                    "hwmid_sum_de_fr": float(row["hwmid_sum"]),
                    "hwmid_method": str(row["hwmid_method"]),
                    "country_cells": int(row["country_cells"]),
                    "source": path.name,
                }
            )

    summary = pd.DataFrame.from_records(records)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    summary.to_csv(args.output, index=False)
    print(args.output)


def resolve_input(input_dir: Path, filenames: list[str]) -> Path:
    for filename in filenames:
        path = input_dir / filename
        if path.exists():
            return path
    formatted = "\n".join(f"- {input_dir / filename}" for filename in filenames)
    raise FileNotFoundError(f"No ranking input found. Tried:\n{formatted}")


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
