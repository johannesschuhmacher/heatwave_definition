"""Run the complete manuscript workflow for E-OBS, ERA5, CMIP5 and CMIP6."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
DEFAULT_EOBS = Path(os.environ.get("HEATWAVE_EOBS_FILE", "data/eobs/tx_ens_mean_0.25deg_reg_v33.0e.nc"))
DEFAULT_ERA5 = Path(os.environ.get("HEATWAVE_ERA5_ROOT", "data/era5/t2m_europe"))
DEFAULT_CMIP5 = Path(os.environ.get("HEATWAVE_CMIP5_ROOT", "data/cordex_cmip5"))
DEFAULT_CMIP6 = Path(os.environ.get("HEATWAVE_CMIP6_ROOT", "data/cordex_cmip6/netcdf"))


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    require(args.eobs_file, "E-OBS v33.0e raw file")
    require(args.era5_root, "ERA5 root directory")
    require(args.cmip5_root, "CORDEX-CMIP5 root directory")
    require(args.cmip6_root, "CORDEX-CMIP6 root directory")

    run(
        [
            sys.executable,
            "scripts/rank_eobs_tx.py",
            str(args.eobs_file),
            "--output",
            "outputs/ranking_from_config/ranked_years_e_obs.csv",
            "--coverage-output",
            "outputs/ranking_from_config/eobs_v33_year_coverage.csv",
            "--top-years",
            str(args.top_years),
        ]
    )
    run(
        [
            sys.executable,
            "scripts/rerun_eobs_v33_historical_sensitivities.py",
            str(args.eobs_file),
            "--top-years",
            "10",
        ]
    )
    eobs_metrics_config = write_eobs_metrics_config(args.eobs_file)
    run([sys.executable, "-m", "heatwave_definition.cli", "run", str(eobs_metrics_config)])

    run(
        [
            sys.executable,
            "scripts/rank_era5_t2m.py",
            str(args.era5_root),
            "--output",
            "outputs/ranking_from_config/ranked_years_era5.csv",
            "--coverage-output",
            "outputs/ranking_from_config/era5_year_coverage.csv",
            "--start-year",
            str(args.era5_start_year),
            "--end-year",
            str(args.era5_end_year),
            "--top-years",
            str(args.top_years),
        ]
    )
    for year, max_date in [(2003, "2003-12-31"), (2026, args.era5_current_max_date)]:
        run(
            [
                sys.executable,
                "scripts/select_era5_automatic_heatwave_windows.py",
                str(args.era5_root),
                "--year",
                str(year),
                "--max-date",
                str(max_date),
            ]
        )
    run([sys.executable, "scripts/make_era5_event_period_comparison.py"])

    if not args.skip_cmip5:
        run(
            [
                sys.executable,
                "scripts/rank_copernicus_ensembles.py",
                "--root",
                str(args.cmip5_root),
                "--top-years",
                str(args.top_years),
            ]
        )
        run([sys.executable, "scripts/summarize_ensemble_rankings.py"])
        run([sys.executable, "scripts/export_primary_cmip5_rankings.py", "--top-years", str(args.top_years)])
        run(
            [
                sys.executable,
                "scripts/rerun_cmip5_primary_sensitivities.py",
                "--root",
                str(args.cmip5_root),
                "--top-years",
                "10",
            ]
        )

    if not args.skip_cmip6:
        command = [
            sys.executable,
            "scripts/rank_cmip6_tas.py",
            "--root",
            str(args.cmip6_root),
            "--top-years",
            "10",
        ]
        if args.cmip6_resume:
            command.append("--resume")
        run(command)

    run([sys.executable, "scripts/summarize_scenario_selection.py"])
    run([sys.executable, "scripts/build_appendix_tables.py"])
    run(
        [
            sys.executable,
            "scripts/make_historical_data_product_comparison.py",
            "--start-year",
            str(args.era5_start_year),
            "--end-year",
            str(args.historical_common_end_year),
        ]
    )
    run([sys.executable, "scripts/make_workflow_example_figure.py", "--metrics", "outputs/raw_metrics/metrics_e_obs.npz"])
    run(
        [
            sys.executable,
            "scripts/make_hwmid_timeseries_example.py",
            "--metrics",
            "outputs/raw_metrics/metrics_e_obs.npz",
            "--eobs",
            str(args.eobs_file),
        ]
    )
    run([sys.executable, "scripts/make_additional_paper_figures.py"])
    run([sys.executable, "scripts/make_cmip6_internal_figures.py", "--output-dir", "outputs/figures"])
    run(
        [
            sys.executable,
            "scripts/write_historical_data_product_manifest.py",
            "--eobs-raw-file",
            str(args.eobs_file),
            "--era5-root",
            str(args.era5_root),
            "--start-year",
            str(args.era5_start_year),
            "--end-year",
            str(args.era5_end_year),
        ]
    )
    run(
        [
            sys.executable,
            "scripts/write_data_manifest.py",
            "--copernicus-root",
            str(args.cmip5_root),
            "--eobs-file",
            str(args.eobs_file),
            "--generated-output",
            "outputs/ensemble_rankings/copernicus2100_de_fr_top_years.csv",
            "--generated-output",
            "outputs/cmip6_internal/cmip6_de_fr_top_years.csv",
        ]
    )
    run([sys.executable, "scripts/snapshot_public_results.py"])
    run([sys.executable, "scripts/check_public_release.py"])


def run(command: list[str]) -> None:
    print("+ " + " ".join(command), flush=True)
    subprocess.run(command, cwd=REPO, check=True)


def require(path: Path, label: str) -> None:
    if not path.exists():
        raise FileNotFoundError(f"Missing {label}: {path}")


def write_eobs_metrics_config(eobs_file: Path) -> Path:
    path = REPO / "outputs" / "provenance" / "e_obs.generated.local.toml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(
            [
                "[run]",
                'name = "e_obs"',
                'data_kind = "e_obs"',
                f'input_file = "{eobs_file.as_posix()}"',
                'output_dir = "outputs/raw_metrics"',
                'countries = ["Germany", "France"]',
                "reference_period = [1981, 2010]",
                "threshold_quantile = 0.90",
                "min_heatwave_days = 3",
                "top_years = 20",
                "",
                "[e_obs]",
                'variable = "tx"',
                'temperature_unit = "degC"',
                "",
            ]
        ),
        encoding="utf-8",
        newline="\n",
    )
    return path


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--eobs-file", type=Path, default=DEFAULT_EOBS)
    parser.add_argument("--era5-root", type=Path, default=DEFAULT_ERA5)
    parser.add_argument("--cmip5-root", type=Path, default=DEFAULT_CMIP5)
    parser.add_argument("--cmip6-root", type=Path, default=DEFAULT_CMIP6)
    parser.add_argument("--era5-start-year", type=int, default=1950)
    parser.add_argument("--era5-end-year", type=int, default=2026)
    parser.add_argument("--historical-common-end-year", type=int, default=2025)
    parser.add_argument("--era5-current-max-date", default="2026-07-01")
    parser.add_argument("--top-years", type=int, default=20)
    parser.add_argument("--skip-cmip5", action="store_true")
    parser.add_argument("--skip-cmip6", action="store_true")
    parser.add_argument("--cmip6-resume", action="store_true")
    return parser.parse_args(argv)


if __name__ == "__main__":
    main()
