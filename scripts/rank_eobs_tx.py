"""Rank E-OBS daily maximum-temperature files by country-mask HWMId."""

from __future__ import annotations

import argparse
from pathlib import Path

from heatwave_definition.raw_eobs import rank_eobs_tx_files


REPO = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = REPO / "outputs" / "ranking_from_config" / "ranked_years_eobs_v33.csv"
DEFAULT_COVERAGE = REPO / "outputs" / "ranking_from_config" / "eobs_v33_year_coverage.csv"


def main() -> None:
    args = parse_args()
    ranking, coverage = rank_eobs_tx_files(
        args.input_files,
        countries=args.countries,
        top_years=args.top_years,
        ref_period=(args.reference_period[0], args.reference_period[1]),
        min_heatwave_days=args.min_heatwave_days,
        threshold_quantile=args.threshold_quantile,
        variable=args.variable,
        temperature_unit=args.temperature_unit,
        min_valid_days_per_year=args.min_valid_days_per_year,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.coverage_output.parent.mkdir(parents=True, exist_ok=True)
    ranking.to_csv(args.output, index=False)
    coverage.to_csv(args.coverage_output, index=False)
    print(args.output)
    print(ranking.to_string(index=False))
    print(args.coverage_output)
    print(coverage.tail(12).to_string(index=False))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_files", type=Path, nargs="+")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--coverage-output", type=Path, default=DEFAULT_COVERAGE)
    parser.add_argument("--countries", nargs="+", default=["Germany", "France"])
    parser.add_argument("--reference-period", type=int, nargs=2, default=[1981, 2010])
    parser.add_argument("--threshold-quantile", type=float, default=0.90)
    parser.add_argument("--min-heatwave-days", type=int, default=3)
    parser.add_argument("--top-years", type=int, default=20)
    parser.add_argument("--variable", default="tx")
    parser.add_argument("--temperature-unit", default="degC", choices=["K", "degC"])
    parser.add_argument("--min-valid-days-per-year", type=int, default=300)
    return parser.parse_args()


if __name__ == "__main__":
    main()
