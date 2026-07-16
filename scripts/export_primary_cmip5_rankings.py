"""Export the manuscript's primary CMIP5 rankings from the ensemble table."""

from __future__ import annotations

import argparse
from pathlib import Path, PureWindowsPath

import pandas as pd


REPO = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = REPO / "outputs" / "ensemble_rankings" / "copernicus2100_de_fr_top_years.csv"
DEFAULT_OUTPUT_DIR = REPO / "outputs" / "ranking_from_config"

PRIMARY_RUNS = [
    {
        "label": "RCP4.5 / IPSL-WRF",
        "scenario": "RCP45",
        "driving_model": "IPSL-IPSL-CM5A-MR",
        "regional_model": "IPSL-WRF381P",
        "run_name": "copernicus_rcp45",
        "output_name": "ranked_years_copernicus_rcp45.csv",
    },
    {
        "label": "RCP8.5 / MPI-CLM",
        "scenario": "RCP85",
        "driving_model": "MPI-M-MPI-ESM-LR",
        "regional_model": "CLMcom-CCLM4-8-17",
        "run_name": "copernicus_rcp85",
        "output_name": "ranked_years_copernicus_rcp85.csv",
    },
]


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    table = pd.read_csv(args.input)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    for spec in PRIMARY_RUNS:
        subset = table[
            (table["scenario"].astype(str).str.upper() == spec["scenario"])
            & (table["driving_model"] == spec["driving_model"])
            & (table["regional_model"] == spec["regional_model"])
        ].copy()
        if subset.empty:
            raise ValueError(f"No ensemble rows found for {spec['label']}")

        subset = subset.sort_values("rank", kind="stable").head(args.top_years)
        source_names = subset.get("source_file", pd.Series([""] * len(subset))).map(source_basename)
        required = ["rank", "year", "hwmid_sum", "hwmid_method", "country_cells", "countries"]
        missing = set(required).difference(subset.columns)
        if missing:
            raise ValueError(f"Ensemble ranking is missing provenance columns: {sorted(missing)}")
        output = subset[required].copy()
        output["aggregation"] = "sum"
        output["run_name"] = spec["run_name"]
        output["source_data"] = "Copernicus/CORDEX-CMIP5 tasAdjust 3-hourly file aggregated to daily Tmax"
        output["source_file_name"] = source_names.to_numpy()

        path = args.output_dir / spec["output_name"]
        output.to_csv(path, index=False)
        print(path)
        print(output.head(2).to_string(index=False))


def source_basename(value: object) -> str:
    text = str(value)
    return PureWindowsPath(text).name if "\\" in text else Path(text).name


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--top-years", type=int, default=20)
    return parser.parse_args(argv)


if __name__ == "__main__":
    main()
