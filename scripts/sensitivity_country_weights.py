"""Run country-weighted sensitivity rankings from metric arrays."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from heatwave_definition.metrics import load_metrics_file, resolve_metrics_file
from heatwave_definition.ranking import rank_years_by_country_weighted_hwmid


REPO = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = REPO / "outputs" / "sensitivity"
DEFAULT_WEIGHTS = REPO / "configs" / "country_weights.example.csv"

DATASETS = [
    ("Historical / E-OBS", ["metrics_e_obs.npz"]),
    ("RCP4.5 / IPSL-WRF", ["metrics_copernicus_rcp45.npz"]),
    ("RCP8.5 / MPI-CLM", ["metrics_copernicus_rcp85.npz"]),
]


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    weights = read_weight_sets(args.weights)

    rows = []
    for dataset, filenames in DATASETS:
        data = load_metrics_file(resolve_metrics_file(args.repo, filenames))
        for weighting, country_weights in weights.items():
            ranking = rank_years_by_country_weighted_hwmid(
                data.latitude,
                data.longitude,
                data.hwmid,
                data.dates,
                country_weights=country_weights,
                no_years=args.top_years,
            )
            ranking.insert(0, "dataset", dataset)
            ranking.insert(1, "weighting", weighting)
            ranking["hwmid_method"] = data.hwmid_method
            rows.append(ranking)

    result = pd.concat(rows, ignore_index=True)
    full_path = args.output_dir / "country_weighted_top_years.csv"
    result.to_csv(full_path, index=False)
    summary_path = args.output_dir / "country_weighted_top2_summary.csv"
    result[result["rank"] <= 2].to_csv(summary_path, index=False)
    print(full_path)
    print(summary_path)


def read_weight_sets(path: Path) -> dict[str, dict[str, float]]:
    table = pd.read_csv(path)
    required = {"weighting", "country", "weight"}
    missing = required.difference(table.columns)
    if missing:
        raise ValueError(f"Weight file is missing columns: {sorted(missing)}")

    result: dict[str, dict[str, float]] = {}
    for weighting, group in table.groupby("weighting"):
        result[str(weighting)] = {
            str(row["country"]): float(row["weight"])
            for _, row in group.iterrows()
            if float(row["weight"]) > 0
        }
    return result


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=REPO)
    parser.add_argument("--weights", type=Path, default=DEFAULT_WEIGHTS)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--top-years", type=int, default=10)
    return parser.parse_args(argv)


if __name__ == "__main__":
    main()
