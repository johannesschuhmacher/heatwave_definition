"""Command line interface for the heatwave definition workflow."""

from __future__ import annotations

import argparse
import sys
import tomllib
from pathlib import Path

import numpy as np

from .hwmid import calc_hwmid
from .legacy import load_legacy_metrics_pickle
from .ranking import rank_years_by_hwmid, write_ranked_years


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="heatwave-definition")
    sub = parser.add_subparsers(dest="command", required=True)

    run_parser = sub.add_parser("run", help="run HWMId analysis from a TOML config")
    run_parser.add_argument("config", type=Path)

    args = parser.parse_args(argv)
    if args.command == "run":
        run_from_config(args.config)
        return 0
    return 2


def run_from_config(config_path: Path) -> None:
    with config_path.open("rb") as handle:
        config = tomllib.load(handle)

    run = config["run"]
    run_name = str(run["name"])
    data_kind = str(run["data_kind"])
    input_file = Path(run["input_file"])
    output_dir = Path(run["output_dir"])
    output_dir.mkdir(parents=True, exist_ok=True)

    if data_kind == "copernicus":
        from .io import load_copernicus_tasadjust_daily_tmax

        data_config = config.get("copernicus", {})
        data = load_copernicus_tasadjust_daily_tmax(
            input_file,
            variable=data_config.get("variable", "tasAdjust"),
            temperature_unit=data_config.get("temperature_unit", "K"),
        )
    elif data_kind == "e_obs":
        from .io import load_e_obs_tmax

        data_config = config.get("e_obs", {})
        data = load_e_obs_tmax(
            input_file,
            variable=data_config.get("variable", "tx"),
            temperature_unit=data_config.get("temperature_unit", "degC"),
        )
    elif data_kind == "metrics_pickle":
        run_existing_metrics(input_file, output_dir, run_name, run)
        return
    else:
        raise ValueError(f"Unsupported data_kind: {data_kind!r}")

    metrics = calc_hwmid(
        data.max_daily_temp,
        data.latitude,
        data.longitude,
        data.dates,
        ref_period=run.get("reference_period", [1981, 2010]),
        min_heatwave_days=int(run.get("min_heatwave_days", 3)),
        threshold_quantile=float(run.get("threshold_quantile", 0.90)),
    )

    metric_path = output_dir / f"metrics_{run_name}.npz"
    np.savez_compressed(
        metric_path,
        hwmid=metrics[0],
        temp_anomaly=metrics[1],
        heatwave_duration=metrics[2],
        temperature_threshold=metrics[3],
        annual_tmax=metrics[4],
        heatwave_start_day=metrics[5],
        heatwave_start_index=metrics[6],
        longitude=np.asarray(data.longitude),
        latitude=np.asarray(data.latitude),
        dates=data.dates.astype("datetime64[ns]").astype("int64"),
    )

    ranking = rank_years_by_hwmid(
        data.latitude,
        data.longitude,
        metrics[0],
        data.dates,
        no_years=int(run.get("top_years", 10)),
        countries=run.get("countries", ["Germany", "France"]),
    )
    ranking_path = output_dir / f"ranked_years_{run_name}.csv"
    write_ranked_years(ranking_path, ranking)

    print(f"Wrote metrics: {metric_path}")
    print(f"Wrote ranking: {ranking_path}")
    print(ranking.to_string(index=False))


def run_existing_metrics(input_file: Path, output_dir: Path, run_name: str, run: dict) -> None:
    """Rank a legacy metrics pickle with the configured country mask.

    This mode is intended for reproducible re-ranking of already computed HWMId
    arrays. It does not recompute HWMId from raw NetCDF input.
    """

    data = load_legacy_metrics_pickle(input_file)

    ranking = rank_years_by_hwmid(
        data.latitude,
        data.longitude,
        data.hwmid,
        data.dates,
        no_years=int(run.get("top_years", 10)),
        countries=run.get("countries", ["Germany", "France"]),
    )
    ranking["run_name"] = run_name
    ranking["source_metrics"] = str(input_file)

    ranking_path = output_dir / f"ranked_years_{run_name}.csv"
    write_ranked_years(ranking_path, ranking)
    print(f"Wrote ranking: {ranking_path}")
    print(ranking.to_string(index=False))


if __name__ == "__main__":
    sys.exit(main())
