"""Select automatic regional heatwave windows from ERA5 HWMId daily signals."""

from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from heatwave_definition.hwmid import _build_threshold_masks, _find_runs
from heatwave_definition.plot_style import apply_manuscript_style, LEGEND_SIZE, TITLE_SIZE


REPO = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = REPO / "outputs" / "era5_current_heatwave"


def main() -> None:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    event_analysis = load_event_analysis_module()

    files = event_analysis.select_files(
        args.input_dir,
        ref_period=(args.reference_period[0], args.reference_period[1]),
        event_year=args.year,
        include_years=args.include_years,
        require_boundary_years=not args.allow_missing_boundary_years,
    )
    daily_tmax, dates, _cell_lat, _cell_lon = event_analysis.load_country_cells(
        files,
        countries=args.countries,
        variable=args.variable,
        temperature_unit=args.temperature_unit,
    )
    daily = build_daily_signal(
        daily_tmax=daily_tmax,
        dates=dates,
        ref_period=(args.reference_period[0], args.reference_period[1]),
        year=args.year,
        threshold_quantile=args.threshold_quantile,
        min_heatwave_days=args.min_heatwave_days,
        max_date=args.max_date,
    )

    windows = select_windows(daily, fixed_window_days=args.fixed_window_days, coverage_threshold=args.coverage_threshold)
    daily_path = args.output_dir / f"era5_de_fr_{args.year}_automatic_daily_signal.csv"
    windows_path = args.output_dir / f"era5_de_fr_{args.year}_automatic_windows.csv"
    figure_path = args.output_dir / f"era5_de_fr_{args.year}_automatic_window_selection.png"
    daily.to_csv(daily_path, index=False)
    windows.to_csv(windows_path, index=False)
    plot_windows(daily, windows, figure_path)

    print(f"Daily signal: {daily_path}")
    print(f"Automatic windows: {windows_path}")
    print(windows.round(3).to_string(index=False))
    print(f"Figure: {figure_path}")


def load_event_analysis_module():
    path = REPO / "scripts" / "analyze_era5_heatwave_event.py"
    spec = importlib.util.spec_from_file_location("event_analysis", path)
    module = importlib.util.module_from_spec(spec)
    if spec.loader is None:
        raise RuntimeError(f"Could not load {path}")
    spec.loader.exec_module(module)
    return module


def build_daily_signal(
    daily_tmax: np.ndarray,
    dates: pd.DatetimeIndex,
    ref_period: tuple[int, int],
    year: int,
    threshold_quantile: float,
    min_heatwave_days: int,
    max_date: pd.Timestamp | None,
) -> pd.DataFrame:
    ref_years = list(range(ref_period[0], ref_period[1] + 1))
    threshold_masks = _build_threshold_masks(dates, ref_years)
    thresholds = np.full((366, daily_tmax.shape[1]), np.nan, dtype=np.float32)
    for day, idx in enumerate(threshold_masks):
        if len(idx):
            thresholds[day, :] = np.nanquantile(daily_tmax[idx, :], threshold_quantile, axis=0)

    ref_annual_max = np.vstack(
        [
            np.nanmax(
                daily_tmax[(dates >= pd.Timestamp(ref_year, 1, 1)) & (dates <= pd.Timestamp(ref_year, 12, 31)), :],
                axis=0,
            )
            for ref_year in ref_years
        ]
    )
    t25 = np.nanquantile(ref_annual_max, 0.25, axis=0)
    denominator = np.nanquantile(ref_annual_max, 0.75, axis=0) - t25
    valid = np.isfinite(denominator) & (denominator > 0)

    day_of_year = dates.dayofyear.to_numpy()
    daily_thresholds = thresholds[day_of_year - 1, :]
    above = np.isfinite(daily_tmax) & (daily_tmax > daily_thresholds)
    daily_magnitude = np.where(
        (daily_tmax > t25[None, :]) & valid[None, :],
        (daily_tmax - t25[None, :]) / denominator[None, :],
        0.0,
    )
    daily_magnitude[~above] = 0.0

    qualifying_daily = np.zeros(len(dates), dtype=float)
    for cell in range(daily_tmax.shape[1]):
        if not valid[cell]:
            continue
        for start_idx, end_idx in _find_runs(above[:, cell], min_heatwave_days):
            qualifying_daily[start_idx : end_idx + 1] += daily_magnitude[start_idx : end_idx + 1, cell]

    year_mask = dates.year == year
    if max_date is not None:
        year_mask = year_mask & (dates <= max_date)
    idx = np.where(year_mask)[0]
    return pd.DataFrame(
        {
            "date": dates[idx].strftime("%Y-%m-%d"),
            "daily_hwmid": qualifying_daily[idx],
            "mean_tmax_c": np.nanmean(daily_tmax[idx, :], axis=1),
            "max_tmax_c": np.nanmax(daily_tmax[idx, :], axis=1),
            "mean_threshold_c": np.nanmean(daily_thresholds[idx, :], axis=1),
            "share_above_threshold": np.count_nonzero(above[idx, :], axis=1) / daily_tmax.shape[1],
        }
    )


def select_windows(daily: pd.DataFrame, fixed_window_days: int, coverage_threshold: float) -> pd.DataFrame:
    daily = daily.copy()
    daily["date"] = pd.to_datetime(daily["date"])
    rows = []

    rolling = daily["daily_hwmid"].rolling(fixed_window_days, min_periods=fixed_window_days).sum()
    end_pos = int(rolling.idxmax())
    start_pos = end_pos - fixed_window_days + 1
    rows.append(window_row("strongest_fixed_window", daily.iloc[start_pos : end_pos + 1]))

    coverage_flags = daily["share_above_threshold"].to_numpy() >= coverage_threshold
    best = None
    for start_pos, end_pos in _find_runs(coverage_flags, 1):
        candidate = daily.iloc[start_pos : end_pos + 1]
        score = float(candidate["daily_hwmid"].sum())
        if best is None or score > best[0]:
            best = (score, candidate)
    if best is not None:
        rows.append(window_row(f"strongest_coverage_ge_{coverage_threshold:g}", best[1]))

    positive_flags = daily["daily_hwmid"].to_numpy() > 0
    best = None
    for start_pos, end_pos in _find_runs(positive_flags, 1):
        candidate = daily.iloc[start_pos : end_pos + 1]
        if (candidate["share_above_threshold"] >= coverage_threshold).any():
            score = float(candidate["daily_hwmid"].sum())
            if best is None or score > best[0]:
                best = (score, candidate)
    if best is not None:
        rows.append(window_row("strongest_positive_run_with_regional_core", best[1]))

    return pd.DataFrame(rows)


def window_row(label: str, frame: pd.DataFrame) -> dict[str, float | int | str]:
    return {
        "selection": label,
        "start": frame["date"].iloc[0].date().isoformat(),
        "end": frame["date"].iloc[-1].date().isoformat(),
        "days": int(len(frame)),
        "hwmid_sum": float(frame["daily_hwmid"].sum()),
        "mean_tmax_c": float(frame["mean_tmax_c"].mean()),
        "max_tmax_c": float(frame["max_tmax_c"].max()),
        "mean_share_above_threshold": float(frame["share_above_threshold"].mean()),
        "max_share_above_threshold": float(frame["share_above_threshold"].max()),
    }


def plot_windows(daily: pd.DataFrame, windows: pd.DataFrame, path: Path) -> None:
    daily = daily.copy()
    daily["date"] = pd.to_datetime(daily["date"])
    apply_manuscript_style()
    fig, axes = plt.subplots(3, 1, figsize=(10.8, 7.2), sharex=True)
    ax0, ax1, ax2 = axes

    ax0.bar(daily["date"], daily["daily_hwmid"], color="#D55E00", alpha=0.42, label="Daily HWMId contribution")
    ax1.plot(daily["date"], daily["mean_tmax_c"], color="#0072B2", linewidth=2.3, label="Mean daily maximum temperature")
    ax1.plot(daily["date"], daily["mean_threshold_c"], color="#009E73", linewidth=1.9, linestyle="--", label="Mean 90th-percentile threshold")
    ax2.plot(daily["date"], daily["share_above_threshold"] * 100, color="#D55E00", linewidth=2.1, label="Cells above threshold")

    colors = {
        "strongest_fixed_window": "#0072B2",
        "strongest_coverage_ge_0.5": "#009E73",
        "strongest_positive_run_with_regional_core": "#CC79A7",
    }
    for _, row in windows.iterrows():
        start = pd.Timestamp(row["start"])
        end = pd.Timestamp(row["end"])
        color = colors.get(str(row["selection"]), "#555555")
        for ax in axes:
            ax.axvspan(start, end, color=color, alpha=0.12)

    ax0.set_ylabel("Daily HWMId")
    ax1.set_ylabel("Temperature (°C)")
    ax2.set_ylabel("Cells above\nthreshold (%)")
    ax2.set_ylim(0, 105)
    ax2.set_xlabel("Date")
    for ax in axes:
        ax.grid(True, axis="y", alpha=0.22)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.legend(frameon=False, loc="upper left", fontsize=LEGEND_SIZE)
    fig.suptitle("Automatic ERA5 heatwave window selection for 2026 over Germany and France", fontsize=TITLE_SIZE, y=0.98)
    fig.tight_layout(rect=[0, 0, 1, 0.95])
    fig.savefig(path, dpi=220)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_dir", type=Path)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--countries", nargs="+", default=["Germany", "France"])
    parser.add_argument("--reference-period", type=int, nargs=2, default=[1981, 2010])
    parser.add_argument("--year", type=int, default=2026)
    parser.add_argument("--include-years", type=int, nargs="*", default=[])
    parser.add_argument("--max-date", type=pd.Timestamp, default=pd.Timestamp("2026-07-01"))
    parser.add_argument("--fixed-window-days", type=int, default=17)
    parser.add_argument("--coverage-threshold", type=float, default=0.5)
    parser.add_argument("--threshold-quantile", type=float, default=0.90)
    parser.add_argument("--min-heatwave-days", type=int, default=3)
    parser.add_argument("--variable", default="t2m")
    parser.add_argument("--temperature-unit", default="K", choices=["K", "degC"])
    parser.add_argument("--allow-missing-boundary-years", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    main()
