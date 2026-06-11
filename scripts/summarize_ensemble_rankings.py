"""Create compact top-2 ensemble ranking tables for the working paper."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


REPO = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = REPO / "outputs" / "ensemble_rankings" / "copernicus2100_de_fr_top_years.csv"
DEFAULT_OUTPUT = REPO / "outputs" / "ensemble_rankings" / "copernicus2100_de_fr_top2_summary.csv"


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    table = pd.read_csv(args.input)
    top2 = table[table["rank"] <= 2].copy()
    top2 = top2[
        [
            "ensemble",
            "scenario",
            "rank",
            "year",
            "hwmid_sum",
            "country_cells",
            "countries",
        ]
    ]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    top2.to_csv(args.output, index=False)
    print(args.output)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args(argv)


if __name__ == "__main__":
    main()
