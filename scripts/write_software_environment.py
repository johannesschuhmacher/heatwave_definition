"""Write a compact software-version manifest for the publication snapshot."""

from __future__ import annotations

import argparse
import platform
import sys
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

import pandas as pd


PACKAGES = [
    "heatwave-definition",
    "numpy",
    "pandas",
    "netCDF4",
    "cftime",
    "Cartopy",
    "Shapely",
    "matplotlib",
    "openpyxl",
    "cdsapi",
    "pytest",
]


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    rows = [
        {"component": "python", "version": platform.python_version()},
        {"component": "platform", "version": platform.platform()},
    ]
    for package in PACKAGES:
        try:
            package_version = version(package)
        except PackageNotFoundError:
            package_version = "not installed"
        rows.append({"component": package, "version": package_version})

    args.output.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(args.output, index=False)
    print(args.output)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("outputs/provenance/software_environment.csv"),
    )
    return parser.parse_args(argv)


if __name__ == "__main__":
    sys.exit(main())
