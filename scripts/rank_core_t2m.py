"""Rank complete NOAA CORe years by Germany-France HWMId.

The partial 2026 comparison with a fixed cutoff is produced by
`compare_reanalysis_rankings.py`.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from heatwave_definition.raw_eobs import rank_eobs_tx_files


REPO = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = REPO / "outputs" / "ranking_from_config" / "ranked_years_core.csv"
DEFAULT_COVERAGE = REPO / "outputs" / "ranking_from_config" / "core_year_coverage.csv"


def main() -> None:
    args = parse_args()
    files = sorted(args.input_dir.glob(args.pattern))
    if not files:
        raise FileNotFoundError(
            f"No CORe files matching {args.pattern!r} found in {args.input_dir}"
        )

    reference_period = tuple(args.reference_period)
    ranking, coverage = rank_eobs_tx_files(
        files,
        countries=args.countries,
        top_years=args.top_years,
        ref_period=reference_period,
        min_heatwave_days=args.min_heatwave_days,
        threshold_quantile=args.threshold_quantile,
        variable=args.variable,
        temperature_unit=args.temperature_unit,
        min_valid_days_per_year=args.min_valid_days_per_year,
    )
    ranking.insert(0, "data_product", "NOAA CORe")
    write_csv(ranking, args.output)
    write_csv(coverage, args.coverage_output)

    print(args.output)
    print(ranking[["rank", "year", "hwmid_sum"]].to_string(index=False))
    print(args.coverage_output)
    print(coverage.tail(5).to_string(index=False))


def write_csv(table, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    table.to_csv(path, index=False)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_dir", type=Path)
    parser.add_argument("--pattern", default="core_t2m_max_europe_*.nc")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--coverage-output", type=Path, default=DEFAULT_COVERAGE)
    parser.add_argument("--countries", nargs="+", default=["Germany", "France"])
    parser.add_argument("--reference-period", type=int, nargs=2, default=[1981, 2010])
    parser.add_argument("--threshold-quantile", type=float, default=0.90)
    parser.add_argument("--min-heatwave-days", type=int, default=3)
    parser.add_argument("--top-years", type=int, default=20)
    parser.add_argument("--variable", default="TMP_2maboveground")
    parser.add_argument("--temperature-unit", default="K", choices=["K", "degC"])
    parser.add_argument("--min-valid-days-per-year", type=int, default=300)
    return parser.parse_args()


if __name__ == "__main__":
    main()
