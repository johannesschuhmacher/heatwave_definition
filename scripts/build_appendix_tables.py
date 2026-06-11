"""Build compact appendix tables from ranking and sensitivity outputs."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


REPO = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = REPO / "outputs" / "appendix"

PRIMARY_RANKINGS = [
    ("Historical / E-OBS", REPO / "outputs" / "ranking_from_config" / "ranked_years_e_obs_from_metrics.csv"),
    ("RCP4.5 / IPSL-WRF", REPO / "outputs" / "ranking_from_config" / "ranked_years_copernicus_rcp45_from_metrics.csv"),
    ("RCP8.5 / MPI-CLM", REPO / "outputs" / "ranking_from_config" / "ranked_years_copernicus_rcp85_from_metrics.csv"),
]


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    top10 = []
    for dataset, path in PRIMARY_RANKINGS:
        table = pd.read_csv(path).head(10)
        table.insert(0, "dataset", dataset)
        top10.append(table[["dataset", "rank", "year", "hwmid_sum", "country_cells"]])
    top10_path = args.output_dir / "primary_top10.csv"
    pd.concat(top10, ignore_index=True).to_csv(top10_path, index=False)

    mask_path = args.output_dir / "country_mask_top2.csv"
    pd.read_csv(args.country_mask).to_csv(mask_path, index=False)

    weighted_path = args.output_dir / "country_weighted_top2.csv"
    pd.read_csv(args.country_weighted).to_csv(weighted_path, index=False)

    criteria_path = args.output_dir / "ranking_criteria_top2.csv"
    pd.read_csv(args.ranking_criteria).to_csv(criteria_path, index=False)

    print(top10_path)
    print(mask_path)
    print(weighted_path)
    print(criteria_path)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--country-mask",
        type=Path,
        default=REPO / "outputs" / "sensitivity" / "country_set_top2_summary.csv",
    )
    parser.add_argument(
        "--country-weighted",
        type=Path,
        default=REPO / "outputs" / "sensitivity" / "country_weighted_top2_summary.csv",
    )
    parser.add_argument(
        "--ranking-criteria",
        type=Path,
        default=REPO / "outputs" / "sensitivity" / "ranking_criteria_top2_summary.csv",
    )
    return parser.parse_args(argv)


if __name__ == "__main__":
    main()
