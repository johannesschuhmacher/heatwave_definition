"""Download ERA5 hourly 2 m temperature files for the HWMId workflow.

The script downloads one NetCDF file per year. Existing files are skipped by
default, so interrupted downloads can be resumed safely.
"""

from __future__ import annotations

import argparse
import calendar
import os
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter


HOURS = [f"{hour:02d}:00" for hour in range(24)]


def main() -> None:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    try:
        import cdsapi
    except ImportError as exc:
        raise SystemExit(
            "Missing optional dependency 'cdsapi'. Install it with: "
            "python -m pip install cdsapi"
        ) from exc

    session = build_session(args.source_address)
    try:
        client = cdsapi.Client(
            url=os.environ.get("COPERNICUS_CDS_URL") or os.environ.get("CDSAPI_URL"),
            key=os.environ.get("COPERNICUS_CDS_KEY") or os.environ.get("CDSAPI_KEY"),
            session=session,
        )
    except Exception as exc:
        raise SystemExit(
            "Could not initialize the CDS API client. Configure CDS credentials "
            "through COPERNICUS_CDS_URL/COPERNICUS_CDS_KEY or in "
            "%USERPROFILE%\\.cdsapirc and accept the ERA5 dataset terms in the "
            "Copernicus Climate Data Store before rerunning this script."
        ) from exc
    start_year = args.start_date.year if args.start_date else args.start_year
    end_year = args.end_date.year if args.end_date else args.end_year

    for year in ordered_years(start_year, end_year, args.priority_years):
        target = args.output_dir / args.target_template.format(year=year)
        if target.exists() and not args.overwrite:
            print(f"Skipping existing file: {target}")
            continue

        months, days_by_month = request_calendar_for_year(year, args.start_date, args.end_date)

        request = {
            "product_type": ["reanalysis"],
            "variable": ["2m_temperature"],
            "year": [str(year)],
            "month": months,
            "day": sorted({day for days in days_by_month.values() for day in days}),
            "time": HOURS,
            "data_format": "netcdf",
            "download_format": "unarchived",
            "area": args.area,
        }
        print(f"Downloading ERA5 t2m {year}: {target}")
        partial = target.with_name(f"{target.name}.partial")
        partial.unlink(missing_ok=True)
        try:
            client.retrieve(args.dataset, request, str(partial))
            partial.replace(target)
        except Exception:
            partial.unlink(missing_ok=True)
            raise


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("data/era5/t2m"))
    parser.add_argument("--start-year", type=int, default=1981)
    parser.add_argument("--end-year", type=int, default=2010)
    parser.add_argument("--start-date", type=parse_date)
    parser.add_argument("--end-date", type=parse_date)
    parser.add_argument("--priority-years", type=int, nargs="*", default=[])
    parser.add_argument("--dataset", default="reanalysis-era5-single-levels")
    parser.add_argument("--target-template", default="t2m_era5_{year}.nc")
    parser.add_argument("--source-address", help="Optional local IPv4 address to bind outgoing HTTPS connections.")
    parser.add_argument(
        "--area",
        type=float,
        nargs=4,
        metavar=("NORTH", "WEST", "SOUTH", "EAST"),
        default=[71.74, -12.26, 32.74, 36.49],
        help="CDS area bounding box. Default matches the local Europe ERA5 files found on endata.",
    )
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


class SourceAddressAdapter(HTTPAdapter):
    """HTTP adapter that binds sockets to a specific local source address."""

    def __init__(self, source_address: str, *args, **kwargs):
        self.source_address = source_address
        super().__init__(*args, **kwargs)

    def init_poolmanager(self, connections, maxsize, block=False, **pool_kwargs):
        pool_kwargs["source_address"] = (self.source_address, 0)
        return super().init_poolmanager(connections, maxsize, block=block, **pool_kwargs)

    def proxy_manager_for(self, proxy, **proxy_kwargs):
        proxy_kwargs["source_address"] = (self.source_address, 0)
        return super().proxy_manager_for(proxy, **proxy_kwargs)


def build_session(source_address: str | None) -> requests.Session:
    session = requests.Session()
    if source_address:
        adapter = SourceAddressAdapter(source_address)
        session.mount("https://", adapter)
        session.mount("http://", adapter)
    return session


def parse_date(value: str):
    from datetime import date

    return date.fromisoformat(value)


def request_calendar_for_year(year: int, start_date, end_date) -> tuple[list[str], dict[str, list[str]]]:
    from datetime import date

    first = date(year, 1, 1)
    last = date(year, 12, 31)
    if start_date is not None and start_date > first:
        first = start_date
    if end_date is not None and end_date < last:
        last = end_date
    if first > last:
        raise ValueError(f"No date range left for {year}")

    months = []
    days_by_month: dict[str, list[str]] = {}
    for month in range(first.month, last.month + 1):
        month_first_day = first.day if month == first.month else 1
        month_last_day = last.day if month == last.month else calendar.monthrange(year, month)[1]
        key = f"{month:02d}"
        months.append(key)
        days_by_month[key] = [f"{day:02d}" for day in range(month_first_day, month_last_day + 1)]
    return months, days_by_month


def ordered_years(start_year: int, end_year: int, priority_years: list[int]) -> list[int]:
    all_years = list(range(start_year, end_year + 1))
    seen = set()
    ordered = []
    for year in priority_years:
        if start_year <= year <= end_year and year not in seen:
            ordered.append(year)
            seen.add(year)
    ordered.extend(year for year in all_years if year not in seen)
    return ordered


if __name__ == "__main__":
    main()
