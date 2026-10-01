"""Extract annual Germany-France ERA5 dewpoint files from a local ERA5 archive.

The source directory may contain arbitrarily chunked hourly `d2m` NetCDF files
(for the manuscript, a mirror on KIT LSDF). `download_era5_dewpoint.py` is the
CDS-based alternative that writes the same annual file layout.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import netCDF4 as nc
import numpy as np
import pandas as pd

from heatwave_definition.io import _decode_time, _first_existing_variable


def main() -> None:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    source_files = sorted(args.source_dir.glob("*.nc"))
    if not source_files:
        raise FileNotFoundError(f"No NetCDF files found in {args.source_dir}")

    coverage = source_coverage(source_files)
    for year in range(args.start_year, args.end_year + 1):
        if year in args.skip_years:
            print(f"Skipping source year {year}")
            continue
        target = args.output_dir / f"d2m_era5_{year}.nc"
        if target.exists() and not args.overwrite:
            print(f"Skipping existing file: {target}")
            continue
        cutoff = pd.Timestamp(args.current_cutoff) if year == args.end_year else pd.Timestamp(year, 12, 31, 23)
        dates, latitude, longitude, values = load_year(
            coverage,
            year,
            cutoff,
            args.area,
        )
        expected_hours = int(((cutoff - pd.Timestamp(year, 1, 1)) / pd.Timedelta(hours=1)) + 1)
        if len(dates) != expected_hours:
            raise ValueError(f"Expected {expected_hours} hourly steps for {year}, found {len(dates)}")
        finite_fraction = float(np.isfinite(values).mean())
        if finite_fraction < 0.99:
            raise ValueError(f"Only {finite_fraction:.1%} finite dewpoint values for {year}")
        write_year(target, dates, latitude, longitude, values)
        print(f"Wrote {target}")


def source_coverage(files: list[Path]) -> list[tuple[Path, pd.Timestamp, pd.Timestamp]]:
    rows = []
    for path in files:
        with nc.Dataset(path) as dataset:
            time_name = _first_existing_variable(dataset, ("valid_time", "time"))
            dates = _decode_time(dataset.variables[time_name])
        rows.append((path, dates.min(), dates.max()))
    return rows


def load_year(
    coverage: list[tuple[Path, pd.Timestamp, pd.Timestamp]],
    year: int,
    cutoff: pd.Timestamp,
    area: list[float],
) -> tuple[pd.DatetimeIndex, np.ndarray, np.ndarray, np.ndarray]:
    start = pd.Timestamp(year, 1, 1)
    date_chunks = []
    value_chunks = []
    expected_latitude = None
    expected_longitude = None
    north, west, south, east = area

    for path, file_start, file_end in coverage:
        if file_end < start or file_start > cutoff:
            continue
        with nc.Dataset(path) as dataset:
            time_name = _first_existing_variable(dataset, ("valid_time", "time"))
            dates = _decode_time(dataset.variables[time_name])
            selected = np.flatnonzero((dates >= start) & (dates <= cutoff))
            if not len(selected):
                continue
            if not np.array_equal(selected, np.arange(selected[0], selected[-1] + 1)):
                raise ValueError(f"Non-contiguous time selection in {path}")

            latitude = np.asarray(dataset.variables["latitude"][:])
            longitude = np.asarray(dataset.variables["longitude"][:])
            lat_positions = np.flatnonzero((latitude >= south) & (latitude <= north))
            lon_positions = np.flatnonzero((longitude >= west) & (longitude <= east))
            lat_slice = contiguous_slice(lat_positions, "latitude", path)
            lon_slice = contiguous_slice(lon_positions, "longitude", path)
            selected_latitude = latitude[lat_slice]
            selected_longitude = longitude[lon_slice]
            values = np.ma.filled(
                dataset.variables["d2m"][selected[0] : selected[-1] + 1, lat_slice, lon_slice],
                np.nan,
            )
            if selected_latitude[0] < selected_latitude[-1]:
                selected_latitude = selected_latitude[::-1]
                values = values[:, ::-1, :]

            if expected_latitude is None:
                expected_latitude = selected_latitude
                expected_longitude = selected_longitude
            elif not (
                np.array_equal(expected_latitude, selected_latitude)
                and np.array_equal(expected_longitude, selected_longitude)
            ):
                raise ValueError(f"Grid changed in {path}")
            date_chunks.append(dates[selected])
            value_chunks.append(values.astype(np.float32))

    if not value_chunks or expected_latitude is None or expected_longitude is None:
        raise ValueError(f"No source data found for {year}")
    dates = pd.DatetimeIndex(np.concatenate([chunk.to_numpy() for chunk in date_chunks]))
    values = np.concatenate(value_chunks, axis=0)
    order = np.argsort(dates.to_numpy())
    return dates[order], expected_latitude, expected_longitude, values[order]


def contiguous_slice(positions: np.ndarray, name: str, path: Path) -> slice:
    if not len(positions) or not np.array_equal(positions, np.arange(positions[0], positions[-1] + 1)):
        raise ValueError(f"Could not select contiguous {name} coordinates from {path}")
    return slice(int(positions[0]), int(positions[-1]) + 1)


def write_year(
    path: Path,
    dates: pd.DatetimeIndex,
    latitude: np.ndarray,
    longitude: np.ndarray,
    values: np.ndarray,
) -> None:
    partial = path.with_name(f"{path.name}.partial")
    partial.unlink(missing_ok=True)
    with nc.Dataset(partial, "w", format="NETCDF4") as dataset:
        dataset.createDimension("valid_time", len(dates))
        dataset.createDimension("latitude", len(latitude))
        dataset.createDimension("longitude", len(longitude))
        time = dataset.createVariable("valid_time", "i8", ("valid_time",))
        time.units = "seconds since 1970-01-01"
        time.calendar = "proleptic_gregorian"
        time[:] = dates.to_numpy(dtype="datetime64[s]").astype(np.int64)
        lat = dataset.createVariable("latitude", "f4", ("latitude",))
        lat.units = "degrees_north"
        lat[:] = latitude
        lon = dataset.createVariable("longitude", "f4", ("longitude",))
        lon.units = "degrees_east"
        lon[:] = longitude
        dewpoint = dataset.createVariable(
            "d2m",
            "f4",
            ("valid_time", "latitude", "longitude"),
            zlib=True,
            complevel=1,
            shuffle=True,
            fill_value=np.nan,
        )
        dewpoint.units = "K"
        dewpoint[:] = values
    partial.replace(path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_dir", type=Path)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--start-year", type=int, default=1981)
    parser.add_argument("--end-year", type=int, default=2026)
    parser.add_argument("--current-cutoff", default="2026-07-01 23:00:00")
    parser.add_argument("--skip-years", type=int, nargs="*", default=[])
    parser.add_argument(
        "--area",
        type=float,
        nargs=4,
        default=[55.25, -5.50, 41.25, 15.50],
        metavar=("NORTH", "WEST", "SOUTH", "EAST"),
    )
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    main()
