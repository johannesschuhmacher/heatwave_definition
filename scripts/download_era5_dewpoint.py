"""Download annual ERA5 hourly 2 m dewpoint files for Germany and France."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys

import cdsapi

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from scripts.download_era5_t2m import (
    HOURS,
    build_session,
    ordered_years,
    request_calendar_for_year,
)


def main() -> None:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    client = cdsapi.Client(
        url=os.environ.get("COPERNICUS_CDS_URL") or os.environ.get("CDSAPI_URL"),
        key=os.environ.get("COPERNICUS_CDS_KEY") or os.environ.get("CDSAPI_KEY"),
        session=build_session(args.source_address),
    )

    for year in ordered_years(args.start_year, args.end_year, args.priority_years):
        target = args.output_dir / f"d2m_era5_{year}.nc"
        if target.exists() and not args.overwrite:
            print(f"Skipping existing file: {target}")
            continue

        months, days_by_month = request_calendar_for_year(
            year,
            args.start_date,
            args.end_date,
        )
        request = {
            "product_type": ["reanalysis"],
            "variable": ["2m_dewpoint_temperature"],
            "year": [str(year)],
            "month": months,
            "day": sorted({day for days in days_by_month.values() for day in days}),
            "time": HOURS,
            "data_format": "netcdf",
            "download_format": "unarchived",
            "area": args.area,
        }
        partial = target.with_name(f"{target.name}.partial")
        partial.unlink(missing_ok=True)
        print(f"Downloading ERA5 d2m {year}: {target}")
        try:
            client.retrieve(args.dataset, request, str(partial))
            partial.replace(target)
        except Exception:
            partial.unlink(missing_ok=True)
            raise


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--start-year", type=int, default=1981)
    parser.add_argument("--end-year", type=int, default=2026)
    parser.add_argument("--start-date", type=lambda value: __import__("datetime").date.fromisoformat(value))
    parser.add_argument("--end-date", type=lambda value: __import__("datetime").date.fromisoformat(value))
    parser.add_argument("--priority-years", type=int, nargs="*", default=[2003, 2026])
    parser.add_argument("--dataset", default="reanalysis-era5-single-levels")
    parser.add_argument("--source-address")
    parser.add_argument(
        "--area",
        type=float,
        nargs=4,
        metavar=("NORTH", "WEST", "SOUTH", "EAST"),
        default=[55.25, -5.50, 41.25, 15.50],
        help="Bounding box covering Germany and metropolitan France on the ERA5 grid.",
    )
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    main()
