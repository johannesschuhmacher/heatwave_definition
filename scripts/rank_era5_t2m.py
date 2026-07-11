"""Rank ERA5 hourly 2 m temperature files by country-mask HWMId."""

from __future__ import annotations

import argparse
from pathlib import Path

from heatwave_definition.raw_era5 import era5_year_coverage, rank_era5_t2m_directory


REPO = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = REPO / "outputs" / "ranking_from_config" / "ranked_years_era5.csv"
DEFAULT_COVERAGE = REPO / "outputs" / "ranking_from_config" / "era5_year_coverage.csv"


def main() -> None:
    args = parse_args()
    ranking = rank_era5_t2m_directory(
        args.input_dir,
        countries=args.countries,
        top_years=args.top_years,
        ref_period=(args.reference_period[0], args.reference_period[1]),
        min_heatwave_days=args.min_heatwave_days,
        threshold_quantile=args.threshold_quantile,
        variable=args.variable,
        temperature_unit=args.temperature_unit,
        pattern=args.pattern,
        start_year=args.start_year,
        end_year=args.end_year,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    ranking.to_csv(args.output, index=False)
    coverage = era5_year_coverage(
        args.input_dir,
        pattern=args.pattern,
        start_year=args.start_year,
        end_year=args.end_year,
    )
    args.coverage_output.parent.mkdir(parents=True, exist_ok=True)
    coverage.to_csv(args.coverage_output, index=False)
    print(args.output)
    print(ranking.to_string(index=False))
    print(args.coverage_output)
    print(coverage.tail(12).to_string(index=False))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_dir", type=Path)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--coverage-output", type=Path, default=DEFAULT_COVERAGE)
    parser.add_argument("--countries", nargs="+", default=["Germany", "France"])
    parser.add_argument("--reference-period", type=int, nargs=2, default=[1981, 2010])
    parser.add_argument("--threshold-quantile", type=float, default=0.90)
    parser.add_argument("--min-heatwave-days", type=int, default=3)
    parser.add_argument("--top-years", type=int, default=10)
    parser.add_argument("--variable", default="t2m")
    parser.add_argument("--temperature-unit", default="K", choices=["K", "degC"])
    parser.add_argument("--pattern", default="t2m_era5_*.nc")
    parser.add_argument("--start-year", type=int)
    parser.add_argument("--end-year", type=int)
    return parser.parse_args()


if __name__ == "__main__":
    main()
