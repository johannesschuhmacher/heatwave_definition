"""Download CORe daily maximum 2 m temperature from the NOAA NODD archive.

The CORe daily FLX files contain a separate ensemble-mean field with the
maximum 2 m temperature over eight three-hour intervals. This script downloads
only that GRIB message, groups the selected messages into annual raw GRIB files,
and creates compact NetCDF subsets covering Germany and France.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import csv
from datetime import date, datetime, timedelta
import os
from pathlib import Path
import re
import shutil
import subprocess
from tempfile import TemporaryDirectory
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import netCDF4 as nc
import numpy as np


BASE_URL = "https://storage.googleapis.com/noaa-nws-ncep-core/grib/day/flx"
FIELD_PATTERN = re.compile(
    r":TMP:2 m above ground:8@3 hour max\(0-3 hour max fcst\),missing=\d+:ens mean"
)
EUROPE_LONGITUDE_RANGE = "-6:16"
EUROPE_LATITUDE_RANGE = "41:56"


def main() -> None:
    args = parse_args()
    start = date.fromisoformat(args.start_date)
    end = date.fromisoformat(args.end_date)
    if end < start:
        raise ValueError("end date must not precede start date")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    raw_dir = args.output_dir / "raw_selected_grib"
    netcdf_dir = args.output_dir / "europe_netcdf"
    parts_dir = args.output_dir / "download_parts"
    raw_dir.mkdir(exist_ok=True)
    netcdf_dir.mkdir(exist_ok=True)
    parts_dir.mkdir(exist_ok=True)

    total_missing: list[date] = []
    for year in range(start.year, end.year + 1):
        year_start = max(start, date(year, 1, 1))
        year_end = min(end, date(year, 12, 31))
        expected_dates = list(date_range(year_start, year_end))
        suffix = str(year) if len(expected_dates) in (365, 366) else f"{year}_through_{year_end:%Y%m%d}"
        raw_path = raw_dir / f"core_t2m_max_{suffix}.grb"
        netcdf_path = netcdf_dir / f"core_t2m_max_europe_{suffix}.nc"
        year_parts = parts_dir / str(year)

        if netcdf_path.exists() and raw_path.exists() and not args.overwrite:
            validate_netcdf(netcdf_path, expected_max_days=len(expected_dates))
            available_dates = set(read_netcdf_dates(netcdf_path))
            total_missing.extend(day for day in expected_dates if day not in available_dates)
            print(f"skip complete {year}: {netcdf_path}")
            continue

        year_parts.mkdir(parents=True, exist_ok=True)
        missing = download_year(
            expected_dates,
            year_parts,
            workers=args.workers,
            retries=args.retries,
        )
        total_missing.extend(missing)
        available_dates = [day for day in expected_dates if day not in set(missing)]
        if not available_dates:
            raise RuntimeError(f"No CORe daily fields were downloaded for {year}")
        if missing and not args.allow_missing:
            write_missing_days(args.output_dir, total_missing)
            raise RuntimeError(
                f"{len(missing)} CORe days are missing in {year}; "
                "rerun with --allow-missing to convert the available dates"
            )

        combine_daily_parts(available_dates, year_parts, raw_path)
        convert_to_europe_netcdf(raw_path, netcdf_path, args.wgrib2, available_dates)
        normalize_time_axis(netcdf_path, available_dates)
        validate_netcdf(netcdf_path, expected_max_days=len(available_dates))
        shutil.rmtree(year_parts)
        print(
            f"complete {year}: {len(available_dates)} days, "
            f"{len(missing)} missing, {netcdf_path}"
        )

    write_missing_days(args.output_dir, total_missing)
    print(f"finished: {start} through {end}; missing days={len(total_missing)}")


def download_year(
    days: list[date],
    output_dir: Path,
    *,
    workers: int,
    retries: int,
) -> list[date]:
    pending = [day for day in days if not daily_part_path(output_dir, day).exists()]
    completed = len(days) - len(pending)
    print(f"{days[0].year}: {completed}/{len(days)} daily fields already present")
    missing: list[date] = []
    if not pending:
        return missing

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(download_daily_field, day, output_dir, retries): day
            for day in pending
        }
        for future in as_completed(futures):
            day = futures[future]
            try:
                found = future.result()
            except Exception as error:
                for remaining in futures:
                    remaining.cancel()
                raise RuntimeError(f"CORe download failed for {day}: {error}") from error
            completed += 1
            if not found:
                missing.append(day)
            if completed % 25 == 0 or completed == len(days):
                print(f"{days[0].year}: {completed}/{len(days)} processed")
    return sorted(missing)


def download_daily_field(day: date, output_dir: Path, retries: int) -> bool:
    output = daily_part_path(output_dir, day)
    base = f"{BASE_URL}/{day:%Y}/{day:%m}/flx.{day:%Y%m%d}"
    try:
        inventory = request_bytes(f"{base}.idx", retries=retries).decode("utf-8")
    except HTTPError as error:
        if error.code == 404:
            return False
        raise

    lines = [line for line in inventory.splitlines() if line]
    selected_index = next(
        (index for index, line in enumerate(lines) if FIELD_PATTERN.search(line)),
        None,
    )
    if selected_index is None:
        return False

    start = byte_offset(lines[selected_index])
    end = next_distinct_offset(lines, selected_index, start)
    range_header = f"bytes={start}-" if end is None else f"bytes={start}-{end - 1}"
    payload = request_bytes(f"{base}.grb", retries=retries, byte_range=range_header)
    if end is not None and len(payload) != end - start:
        raise IOError(
            f"byte-range length mismatch: expected {end - start}, received {len(payload)}"
        )
    temporary = output.with_suffix(".grb.tmp")
    temporary.write_bytes(payload)
    temporary.replace(output)
    return True


def request_bytes(url: str, *, retries: int, byte_range: str | None = None) -> bytes:
    for attempt in range(retries + 1):
        request = Request(url)
        if byte_range is not None:
            request.add_header("Range", byte_range)
        try:
            with urlopen(request, timeout=60) as response:
                return response.read()
        except HTTPError as error:
            if error.code == 404 or attempt == retries:
                raise
        except (URLError, TimeoutError, ConnectionError):
            if attempt == retries:
                raise
        time.sleep(min(2**attempt, 20))
    raise AssertionError("retry loop exited unexpectedly")


def byte_offset(inventory_line: str) -> int:
    parts = inventory_line.split(":", 2)
    if len(parts) < 2:
        raise ValueError(f"invalid CORe inventory line: {inventory_line!r}")
    return int(parts[1])


def next_distinct_offset(lines: list[str], selected_index: int, start: int) -> int | None:
    for line in lines[selected_index + 1 :]:
        offset = byte_offset(line)
        if offset != start:
            return offset
    return None


def daily_part_path(output_dir: Path, day: date) -> Path:
    return output_dir / f"core_t2m_max_{day:%Y%m%d}.grb"


def combine_daily_parts(days: list[date], parts_dir: Path, output: Path) -> None:
    temporary = output.with_suffix(".grb.tmp")
    with temporary.open("wb") as destination:
        for day in days:
            with daily_part_path(parts_dir, day).open("rb") as source:
                shutil.copyfileobj(source, destination)
    temporary.replace(output)


def convert_to_europe_netcdf(
    raw_grib: Path,
    output: Path,
    wgrib2: Path,
    days: list[date],
) -> None:
    temporary_grib = output.with_suffix(".europe.grb.tmp")
    temporary_netcdf = output.with_suffix(".nc.tmp")
    environment = {**os.environ, "OMP_NUM_THREADS": "2"}
    subprocess.run(
        [
            str(wgrib2),
            str(raw_grib),
            "-small_grib",
            EUROPE_LONGITUDE_RANGE,
            EUROPE_LATITUDE_RANGE,
            str(temporary_grib),
        ],
        check=True,
        capture_output=True,
        text=True,
        env=environment,
    )
    try:
        try:
            run_wgrib2(
                [str(temporary_grib), "-netcdf", str(temporary_netcdf)],
                wgrib2,
                environment,
            )
        except subprocess.CalledProcessError:
            # The Windows wgrib2 build can reject annual files whose valid
            # times approach the Unix epoch. Smaller chunks avoid that bug.
            temporary_netcdf.unlink(missing_ok=True)
            convert_in_chunks(
                temporary_grib,
                temporary_netcdf,
                wgrib2,
                environment,
                days,
            )
        temporary_netcdf.replace(output)
    finally:
        temporary_grib.unlink(missing_ok=True)


def convert_in_chunks(
    grib: Path,
    output: Path,
    wgrib2: Path,
    environment: dict[str, str],
    days: list[date],
) -> None:
    chunks: list[Path] = []
    months = sorted({(day.year, day.month) for day in days})
    with TemporaryDirectory(prefix="core_netcdf_", dir=output.parent) as temporary_dir:
        directory = Path(temporary_dir)
        for year, month in months:
            month_days = [day for day in days if (day.year, day.month) == (year, month)]
            month_grib = directory / f"{year}{month:02d}.grb"
            month_netcdf = directory / f"{year}{month:02d}.nc"
            select_grib_records(
                grib,
                month_grib,
                f"d={year}{month:02d}",
                wgrib2,
                environment,
            )
            try:
                run_wgrib2(
                    [str(month_grib), "-netcdf", str(month_netcdf)],
                    wgrib2,
                    environment,
                )
                chunks.append(month_netcdf)
            except subprocess.CalledProcessError:
                month_netcdf.unlink(missing_ok=True)
                for day in month_days:
                    day_grib = directory / f"{day:%Y%m%d}.grb"
                    day_netcdf = directory / f"{day:%Y%m%d}.nc"
                    select_grib_records(
                        grib,
                        day_grib,
                        f"d={day:%Y%m%d}",
                        wgrib2,
                        environment,
                    )
                    try:
                        run_wgrib2(
                            [str(day_grib), "-netcdf", str(day_netcdf)],
                            wgrib2,
                            environment,
                        )
                    except subprocess.CalledProcessError:
                        day_netcdf.unlink(missing_ok=True)
                        convert_grib_record_via_csv(
                            day_grib,
                            day_netcdf,
                            wgrib2,
                            environment,
                        )
                    chunks.append(day_netcdf)

        merge_netcdf_chunks(chunks, output)


def select_grib_records(
    source: Path,
    output: Path,
    match: str,
    wgrib2: Path,
    environment: dict[str, str],
) -> None:
    run_wgrib2(
        [str(source), "-match", match, "-grib", str(output)],
        wgrib2,
        environment,
    )
    if not output.exists() or output.stat().st_size == 0:
        raise RuntimeError(f"wgrib2 selected no records matching {match!r}")


def run_wgrib2(
    arguments: list[str],
    executable: Path,
    environment: dict[str, str],
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(executable), *arguments],
        check=True,
        capture_output=True,
        text=True,
        env=environment,
    )


def merge_netcdf_chunks(chunks: list[Path], output: Path) -> None:
    if not chunks:
        raise ValueError("no NetCDF chunks to merge")

    template_path = max(chunks, key=netcdf_time_length)
    with nc.Dataset(template_path) as template, nc.Dataset(output, "w") as destination:
        latitude = template.variables["latitude"]
        longitude = template.variables["longitude"]
        temperature = template.variables["TMP_2maboveground"]

        destination.createDimension("latitude", len(latitude))
        destination.createDimension("longitude", len(longitude))
        destination.createDimension("time", None)
        output_latitude = destination.createVariable("latitude", "f8", ("latitude",))
        output_longitude = destination.createVariable("longitude", "f8", ("longitude",))
        output_time = destination.createVariable("time", "f8", ("time",))
        output_temperature = destination.createVariable(
            "TMP_2maboveground",
            "f4",
            ("time", "latitude", "longitude"),
            fill_value=getattr(temperature, "_FillValue", 9.999e20),
            zlib=True,
            complevel=4,
        )

        output_latitude[:] = latitude[:]
        output_longitude[:] = longitude[:]
        copy_attributes(latitude, output_latitude)
        copy_attributes(longitude, output_longitude)
        copy_attributes(temperature, output_temperature, exclude={"_FillValue"})
        output_time.units = "days since 1900-01-01 00:00:00"
        output_time.calendar = "standard"
        destination.Conventions = "COARDS"
        destination.History = "created from monthly CORe wgrib2 NetCDF chunks"

        offset = 0
        for chunk in chunks:
            with nc.Dataset(chunk) as source:
                if not np.allclose(source.variables["latitude"][:], latitude[:], atol=1e-4):
                    raise ValueError(f"latitude grid changed in NetCDF chunk {chunk}")
                if not np.allclose(source.variables["longitude"][:], longitude[:], atol=1e-4):
                    raise ValueError(f"longitude grid changed in NetCDF chunk {chunk}")
                values = source.variables["TMP_2maboveground"]
                count = values.shape[0]
                output_temperature[offset : offset + count, :, :] = values[:, :, :]
                output_time[offset : offset + count] = np.arange(offset, offset + count)
                offset += count


def netcdf_time_length(path: Path) -> int:
    with nc.Dataset(path) as dataset:
        return len(dataset.dimensions["time"])


def convert_grib_record_via_csv(
    grib: Path,
    output: Path,
    wgrib2: Path,
    environment: dict[str, str],
) -> None:
    csv_path = output.with_suffix(".csv")
    try:
        run_wgrib2(
            [str(grib), "-csv", str(csv_path)],
            wgrib2,
            environment,
        )
        with csv_path.open(newline="", encoding="ascii") as source:
            rows = list(csv.reader(source))

        point_longitudes = np.array([float(row[4]) for row in rows])
        point_latitudes = np.array([float(row[5]) for row in rows])
        longitude = np.unique(point_longitudes)
        latitude = np.unique(point_latitudes)
        expected_size = len(latitude) * len(longitude)
        if len(rows) != expected_size:
            raise ValueError(
                f"expected {expected_size} CSV grid points, found {len(rows)}"
            )
        values = np.full((len(latitude), len(longitude)), np.nan, dtype="f4")
        values[
            np.searchsorted(latitude, point_latitudes),
            np.searchsorted(longitude, point_longitudes),
        ] = np.array([float(row[6]) for row in rows], dtype="f4")

        with nc.Dataset(output, "w") as destination:
            destination.createDimension("latitude", len(latitude))
            destination.createDimension("longitude", len(longitude))
            destination.createDimension("time", None)
            output_latitude = destination.createVariable("latitude", "f8", ("latitude",))
            output_longitude = destination.createVariable(
                "longitude", "f8", ("longitude",)
            )
            output_time = destination.createVariable("time", "f8", ("time",))
            output_temperature = destination.createVariable(
                "TMP_2maboveground",
                "f4",
                ("time", "latitude", "longitude"),
                fill_value=9.999e20,
            )
            output_latitude[:] = latitude
            output_longitude[:] = longitude
            output_time[:] = [0]
            output_temperature[0, :, :] = values
            output_latitude.units = "degrees_north"
            output_latitude.long_name = "latitude"
            output_longitude.units = "degrees_east"
            output_longitude.long_name = "longitude"
            output_time.units = "days since 1900-01-01 00:00:00"
            output_time.calendar = "standard"
            output_temperature.short_name = "TMP_2maboveground"
            output_temperature.long_name = "Temperature"
            output_temperature.level = "2 m above ground"
            output_temperature.units = "K"
    finally:
        csv_path.unlink(missing_ok=True)


def copy_attributes(source, destination, *, exclude: set[str] | None = None) -> None:
    excluded = exclude or set()
    for attribute in source.ncattrs():
        if attribute not in excluded:
            destination.setncattr(attribute, source.getncattr(attribute))


def validate_netcdf(path: Path, *, expected_max_days: int) -> None:
    with nc.Dataset(path) as dataset:
        if "TMP_2maboveground" not in dataset.variables:
            raise ValueError(f"CORe temperature variable missing from {path}")
        values = dataset.variables["TMP_2maboveground"]
        if not 1 <= values.shape[0] <= expected_max_days:
            raise ValueError(
                f"unexpected time length in {path}: {values.shape[0]} of {expected_max_days}"
            )
        sample = np.ma.filled(values[0, :, :], np.nan)
        if not np.isfinite(sample).any() or np.nanmin(sample) < 180 or np.nanmax(sample) > 350:
            raise ValueError(f"implausible 2 m temperature values in {path}")


def read_netcdf_dates(path: Path) -> list[date]:
    with nc.Dataset(path) as dataset:
        time_variable = dataset.variables["time"]
        timestamps = nc.num2date(
            time_variable[:],
            units=time_variable.units,
            calendar=getattr(time_variable, "calendar", "standard"),
        )
    return [date(timestamp.year, timestamp.month, timestamp.day) for timestamp in timestamps]


def normalize_time_axis(path: Path, days: list[date]) -> None:
    with nc.Dataset(path, "r+") as dataset:
        time_variable = dataset.variables["time"]
        if len(time_variable) != len(days):
            raise ValueError(
                f"cannot assign {len(days)} dates to {len(time_variable)} records in {path}"
            )
        calendar = getattr(time_variable, "calendar", "standard")
        timestamps = [datetime.combine(day, datetime.min.time()) for day in days]
        time_variable[:] = nc.date2num(
            timestamps,
            units=time_variable.units,
            calendar=calendar,
        )
        time_variable.calendar = calendar
        dataset.daily_statistic = (
            "ensemble-mean maximum 2 m temperature across eight three-hour intervals"
        )
        dataset.source = "NOAA Conventional Observation Reanalysis (CORe) NODD archive"
        dataset.source_url = BASE_URL


def write_missing_days(output_dir: Path, missing: list[date]) -> None:
    path = output_dir / "missing_days.txt"
    if missing:
        path.write_text("".join(f"{day.isoformat()}\n" for day in sorted(set(missing))), encoding="ascii")
    else:
        path.unlink(missing_ok=True)


def date_range(start: date, end: date):
    day = start
    while day <= end:
        yield day
        day += timedelta(days=1)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--start-date", default="1950-01-01")
    parser.add_argument("--end-date", default=(datetime.now().date() - timedelta(days=2)).isoformat())
    parser.add_argument("--workers", type=int, default=8, choices=range(1, 33))
    parser.add_argument("--retries", type=int, default=5)
    parser.add_argument("--allow-missing", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--wgrib2", type=Path, required=True)
    args = parser.parse_args()
    if not args.wgrib2.exists():
        parser.error(f"wgrib2 executable not found: {args.wgrib2}")
    return args


if __name__ == "__main__":
    main()
