"""Copy curated derived outputs into the versioned results directory."""

from __future__ import annotations

import csv
import shutil
from pathlib import Path, PureWindowsPath


REPO = Path(__file__).resolve().parents[1]
OUTPUTS = REPO / "outputs"
RESULTS = REPO / "results"

FILES = [
    ("appendix/primary_top10.csv", "tables/primary_top10.csv"),
    ("appendix/country_mask_top2.csv", "tables/country_mask_top2.csv"),
    ("appendix/country_weighted_top2.csv", "tables/country_weighted_top2.csv"),
    ("appendix/ranking_criteria_top2.csv", "tables/ranking_criteria_top2.csv"),
    ("ranking_from_config/scenario_selection_summary.csv", "rankings/scenario_selection_summary.csv"),
    ("ranking_from_config/ranked_years_e_obs_from_metrics.csv", "rankings/ranked_years_e_obs_from_metrics.csv"),
    ("ranking_from_config/ranked_years_copernicus_rcp45_from_metrics.csv", "rankings/ranked_years_copernicus_rcp45_from_metrics.csv"),
    ("ranking_from_config/ranked_years_copernicus_rcp85_from_metrics.csv", "rankings/ranked_years_copernicus_rcp85_from_metrics.csv"),
    ("ensemble_rankings/copernicus2100_de_fr_top2_summary.csv", "ensemble/copernicus2100_de_fr_top2_summary.csv"),
    ("ensemble_rankings/copernicus2100_de_fr_top_years.csv", "ensemble/copernicus2100_de_fr_top_years.csv"),
    ("sensitivity/country_set_top2_summary.csv", "sensitivity/country_set_top2_summary.csv"),
    ("sensitivity/country_set_top_years.csv", "sensitivity/country_set_top_years.csv"),
    ("sensitivity/country_weighted_top2_summary.csv", "sensitivity/country_weighted_top2_summary.csv"),
    ("sensitivity/country_weighted_top_years.csv", "sensitivity/country_weighted_top_years.csv"),
    ("sensitivity/country_weights_from_tyndp2024_pemmdb_nt2040.csv", "sensitivity/country_weights_from_tyndp2024_pemmdb_nt2040.csv"),
    ("sensitivity/ranking_criteria_top2_summary.csv", "sensitivity/ranking_criteria_top2_summary.csv"),
    ("sensitivity/ranking_criteria_top_years.csv", "sensitivity/ranking_criteria_top_years.csv"),
    ("sensitivity/tyndp_pemmdb_vs_eraa2024_wce_comparison.csv", "validation/tyndp_pemmdb_vs_eraa2024_wce_comparison.csv"),
    ("sensitivity/tyndp_pemmdb_vs_supply_inputs_comparison.csv", "validation/tyndp_pemmdb_vs_supply_inputs_comparison.csv"),
    ("sensitivity/tyndp_pemmdb_vs_supply_inputs_comparison_by_country.csv", "validation/tyndp_pemmdb_vs_supply_inputs_comparison_by_country.csv"),
    ("figures/top10_rank_curve_de_fr.png", "figures/top10_rank_curve_de_fr.png"),
    ("figures/scenario_hwmid_top2_de_fr.png", "figures/scenario_hwmid_top2_de_fr.png"),
    ("figures/country_mask_top2_heatmap.png", "figures/country_mask_top2_heatmap.png"),
    ("figures/n_minus_1_top2_heatmap.png", "figures/n_minus_1_top2_heatmap.png"),
    ("figures/technology_weighting_top2_heatmap.png", "figures/technology_weighting_top2_heatmap.png"),
    ("figures/ranking_criteria_top2_heatmap_de_fr.png", "figures/ranking_criteria_top2_heatmap_de_fr.png"),
    ("figures/ensemble_top2_dotplot.png", "figures/ensemble_top2_dotplot.png"),
    ("figures/method_flow_diagram.png", "figures/method_flow_diagram.png"),
]

SANITIZED_CSVS = {
    "ensemble/copernicus2100_de_fr_top_years.csv",
}


README = """# Versioned results

This directory contains a curated snapshot of derived result tables and figures
used by the heatwave scenario-definition manuscript. Raw meteorological data,
trusted legacy metric pickles, local data manifests, provider downloads and
large intermediate arrays are intentionally not included.
Local source paths are stripped from copied tables; where useful, only the
source file name is retained for provenance.

The files are copied from `outputs/` with:

```bash
python scripts/snapshot_public_results.py
```

Contents:

- `rankings/`: primary scenario-year rankings.
- `sensitivity/`: country-mask, weighting and ranking-criterion sensitivity outputs.
- `ensemble/`: Copernicus raw-data ensemble sensitivity summaries.
- `tables/`: appendix-ready compact tables.
- `figures/`: manuscript and supplementary figures.
- `validation/`: TYNDP 2024 PEMMDB capacity cross-check tables.
"""


def main() -> None:
    missing = []
    for source, target in FILES:
        source_path = OUTPUTS / source
        target_path = RESULTS / target
        if not source_path.exists():
            missing.append(source)
            continue
        target_path.parent.mkdir(parents=True, exist_ok=True)
        if target in SANITIZED_CSVS:
            copy_sanitized_csv(source_path, target_path)
        else:
            shutil.copy2(source_path, target_path)

    (RESULTS / "README.md").write_text(README, encoding="utf-8", newline="\n")

    if missing:
        formatted = "\n".join(f"- {path}" for path in missing)
        raise FileNotFoundError(f"Missing expected output files:\n{formatted}")

    print(RESULTS)


def copy_sanitized_csv(source_path: Path, target_path: Path) -> None:
    with source_path.open("r", encoding="utf-8", newline="") as source_file:
        reader = csv.DictReader(source_file)
        if reader.fieldnames is None:
            raise ValueError(f"CSV file has no header: {source_path}")

        fieldnames = list(reader.fieldnames)
        if "source_file" in fieldnames:
            source_index = fieldnames.index("source_file")
            fieldnames.pop(source_index)
            if "source_file_name" not in fieldnames:
                fieldnames.insert(source_index, "source_file_name")

        rows = []
        for row in reader:
            source_file_value = row.pop("source_file", "")
            if source_file_value:
                row["source_file_name"] = source_basename(source_file_value)
            rows.append({name: row.get(name, "") for name in fieldnames})

    with target_path.open("w", encoding="utf-8", newline="") as target_file:
        writer = csv.DictWriter(target_file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def source_basename(value: str) -> str:
    return PureWindowsPath(value).name if "\\" in value else Path(value).name


if __name__ == "__main__":
    main()
