"""Rank Copernicus2100 tasAdjust ensemble files by DE+FR HWMId."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

import pandas as pd

from heatwave_definition.raw_copernicus import (
    discover_tasadjust_runs,
    rank_copernicus_tasadjust_file,
)


REPO = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = REPO / "outputs" / "ensemble_rankings" / "copernicus2100_de_fr_top_years.csv"


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    if args.root is None:
        raise SystemExit("Provide --root or set HEATWAVE_COPERNICUS_ROOT.")
    args.output.parent.mkdir(parents=True, exist_ok=True)

    runs = discover_tasadjust_runs(args.root)
    if args.scenario:
        scenarios = {scenario.upper().replace(".", "") for scenario in args.scenario}
        runs = [run for run in runs if run.scenario.replace(".", "") in scenarios]
    if args.model:
        models = {model.lower() for model in args.model}
        runs = [
            run
            for run in runs
            if run.driving_model.lower() in models or run.regional_model.lower() in models
        ]
    if args.max_files is not None:
        runs = runs[: args.max_files]

    all_rows = []
    for idx, run in enumerate(runs, start=1):
        print(f"[{idx}/{len(runs)}] {run.label}")
        ranking = rank_copernicus_tasadjust_file(
            run.path,
            countries=args.countries,
            top_years=args.top_years,
            ref_period=tuple(args.reference_period),
            min_heatwave_days=args.min_heatwave_days,
            threshold_quantile=args.threshold_quantile,
        )
        ranking.insert(0, "ensemble", run.label)
        ranking.insert(1, "scenario", run.scenario)
        ranking.insert(2, "driving_model", run.driving_model)
        ranking.insert(3, "regional_model", run.regional_model)
        all_rows.append(ranking)

        pd.concat(all_rows, ignore_index=True).to_csv(args.output, index=False)
        print(ranking.head(args.top_years).to_string(index=False))
        print(f"Wrote partial results: {args.output}")

    if not all_rows:
        raise SystemExit(f"No tasAdjust runs found below {args.root}")

    result = pd.concat(all_rows, ignore_index=True)
    result.to_csv(args.output, index=False)
    print(f"Wrote results: {args.output}")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(os.environ["HEATWAVE_COPERNICUS_ROOT"])
        if "HEATWAVE_COPERNICUS_ROOT" in os.environ
        else None,
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--countries", nargs="+", default=["Germany", "France"])
    parser.add_argument("--top-years", type=int, default=10)
    parser.add_argument("--reference-period", nargs=2, type=int, default=[1981, 2010])
    parser.add_argument("--min-heatwave-days", type=int, default=3)
    parser.add_argument("--threshold-quantile", type=float, default=0.90)
    parser.add_argument("--scenario", nargs="*", help="Optional scenario filter, e.g. rcp45 rcp85")
    parser.add_argument("--model", nargs="*", help="Optional driving or regional model filter")
    parser.add_argument("--max-files", type=int, help="Process only the first N discovered files")
    return parser.parse_args(argv)


if __name__ == "__main__":
    main()
