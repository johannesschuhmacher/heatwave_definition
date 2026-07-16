"""Plot workflow-selected ERA5 heatwave periods for 2003 and 2026."""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
from matplotlib.lines import Line2D
import pandas as pd

from heatwave_definition.hwmid import HWMID_METHOD_ID
from heatwave_definition.plot_style import (
    ANNOTATION_SIZE,
    AXIS_LABEL_SIZE,
    LEGEND_SIZE,
    PANEL_TITLE_SIZE,
    SUBTITLE_SIZE,
    TITLE_SIZE,
    apply_manuscript_style,
)


REPO = Path(__file__).resolve().parents[1]
DEFAULT_INPUT_DIR = REPO / "outputs" / "era5_current_heatwave"
DEFAULT_FIGURE = DEFAULT_INPUT_DIR / "era5_de_fr_2003_2026_event_period_comparison.png"
DEFAULT_SUMMARY = DEFAULT_INPUT_DIR / "era5_de_fr_2003_2026_event_period_summary.csv"
DEFAULT_RESULTS_FIGURE = REPO / "results" / "figures" / "era5_2003_2026_event_period_comparison.png"

YEARS = [2003, 2026]
YEAR_COLORS = {2003: "#0072B2", 2026: "#D55E00"}
SHARE_COLOR = "#009E73"
THRESHOLD_COLOR = "#4D4D4D"
ENVELOPE_COLOR = "#D9D9D9"
CORE_COLOR = "#F0E6A6"


def main() -> None:
    args = parse_args()
    records = {}
    summary_rows = []
    for year in YEARS:
        daily, windows = load_year(args.input_dir, year)
        records[year] = (daily, windows)
        summary_rows.append(summarize_year(daily, windows, year))

    summary = pd.DataFrame(summary_rows)
    args.summary_output.parent.mkdir(parents=True, exist_ok=True)
    summary.to_csv(args.summary_output, index=False)
    plot_comparison(records, args.figure_output)
    if args.results_figure_output:
        args.results_figure_output.parent.mkdir(parents=True, exist_ok=True)
        plot_comparison(records, args.results_figure_output)

    print(args.summary_output)
    print(summary.round(3).to_string(index=False))
    print(args.figure_output)
    if args.results_figure_output:
        print(args.results_figure_output)


def load_year(input_dir: Path, year: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    daily_path = input_dir / f"era5_de_fr_{year}_automatic_daily_signal.csv"
    windows_path = input_dir / f"era5_de_fr_{year}_automatic_windows.csv"
    daily = pd.read_csv(daily_path)
    windows = pd.read_csv(windows_path)
    daily["date"] = pd.to_datetime(daily["date"])
    return daily, windows


def summarize_year(daily: pd.DataFrame, windows: pd.DataFrame, year: int) -> dict[str, object]:
    envelope = select_window(windows, "strongest_positive_run_with_regional_core")
    core = select_window(windows, "strongest_coverage_ge_0.5")
    fixed = select_window(windows, "strongest_fixed_window")
    core_daily = subset_window(daily, core)
    envelope_daily = subset_window(daily, envelope)
    return {
        "year": year,
        "event_period_start": envelope["start"],
        "event_period_end": envelope["end"],
        "event_period_days": int(envelope["days"]),
        "event_period_contribution_sum": float(envelope["regional_hwmid_contribution_sum"]),
        "hwmid_method": HWMID_METHOD_ID,
        "regional_core_start": core["start"],
        "regional_core_end": core["end"],
        "regional_core_days": int(core["days"]),
        "regional_core_contribution_sum": float(core["regional_hwmid_contribution_sum"]),
        "fixed_17_day_start": fixed["start"],
        "fixed_17_day_end": fixed["end"],
        "fixed_17_day_contribution_sum": float(fixed["regional_hwmid_contribution_sum"]),
        "regional_core_mean_tmax_c": float(core_daily["mean_tmax_c"].mean()),
        "regional_core_max_tmax_c": float(core_daily["max_tmax_c"].max()),
        "regional_core_mean_cells_above_threshold": float(core_daily["share_above_threshold"].mean()),
        "event_period_mean_cells_above_threshold": float(envelope_daily["share_above_threshold"].mean()),
    }


def select_window(windows: pd.DataFrame, selection: str) -> pd.Series:
    match = windows.loc[windows["selection"] == selection]
    if match.empty:
        raise ValueError(f"Missing window selection {selection!r}")
    return match.iloc[0]


def subset_window(daily: pd.DataFrame, window: pd.Series) -> pd.DataFrame:
    start = pd.Timestamp(window["start"])
    end = pd.Timestamp(window["end"])
    return daily[(daily["date"] >= start) & (daily["date"] <= end)].copy()


def plot_comparison(records: dict[int, tuple[pd.DataFrame, pd.DataFrame]], output: Path) -> None:
    apply_manuscript_style()
    fig, axes = plt.subplots(2, 2, figsize=(11.2, 6.9), sharey="row")
    deg_c = chr(176) + "C"

    max_hwmid = max(daily["daily_hwmid"].max() for daily, _windows in records.values())
    for col, year in enumerate(YEARS):
        daily, windows = records[year]
        envelope = select_window(windows, "strongest_positive_run_with_regional_core")
        core = select_window(windows, "strongest_coverage_ge_0.5")
        plot_daily_panel(axes[0, col], daily, envelope, core, year, max_hwmid)
        plot_temperature_panel(axes[1, col], daily, envelope, core, year, deg_c)

    axes[0, 0].set_ylabel("Daily HWMId\ncontribution", fontsize=AXIS_LABEL_SIZE)
    axes[1, 0].set_ylabel(f"Mean temperature ({deg_c})", fontsize=AXIS_LABEL_SIZE)
    for ax in axes[1, :]:
        ax.set_xlabel("Date", fontsize=AXIS_LABEL_SIZE)

    legend_handles = [
        Patch(facecolor=ENVELOPE_COLOR, edgecolor="none", alpha=0.35, label="workflow-selected event period"),
        Patch(facecolor=CORE_COLOR, edgecolor="none", alpha=0.55, label="regional core (at least 50% of cells above threshold)"),
        Line2D([0], [0], color=SHARE_COLOR, linewidth=2.0, label="cells above threshold"),
        Line2D([0], [0], color=THRESHOLD_COLOR, linewidth=1.8, linestyle="--", label="mean 90th-percentile threshold"),
    ]
    fig.legend(
        handles=legend_handles,
        frameon=False,
        loc="lower center",
        bbox_to_anchor=(0.5, -0.015),
        ncol=2,
        fontsize=LEGEND_SIZE,
    )
    fig.suptitle(
        "Workflow-selected ERA5 heatwave periods for the 2003 and 2026 benchmark events",
        fontsize=TITLE_SIZE,
        y=0.985,
    )
    fig.text(
        0.5,
        0.945,
        "Windows are selected separately using the same regional signal; values sum contributions from qualifying local events.",
        ha="center",
        va="top",
        fontsize=SUBTITLE_SIZE,
        color="#555555",
    )
    fig.tight_layout(rect=[0, 0.055, 1, 0.91])
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, dpi=220)
    plt.close(fig)


def plot_daily_panel(
    ax,
    daily: pd.DataFrame,
    envelope: pd.Series,
    core: pd.Series,
    year: int,
    max_hwmid: float,
) -> None:
    view = event_view(daily, envelope)
    shade_windows(ax, envelope, core)
    ax.bar(view["date"], view["daily_hwmid"], color=YEAR_COLORS[year], alpha=0.82, width=0.8)
    ax.set_ylim(0, max_hwmid * 1.14)
    ax.set_title(
        event_title(year, envelope, core),
        fontsize=PANEL_TITLE_SIZE,
        loc="left",
        pad=7,
    )
    ax.grid(True, axis="y", alpha=0.22)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    share_ax = ax.twinx()
    share_ax.plot(
        view["date"],
        view["share_above_threshold"] * 100,
        color=SHARE_COLOR,
        linewidth=1.9,
    )
    share_ax.axhline(50, color=SHARE_COLOR, linewidth=1.0, linestyle=":", alpha=0.7)
    share_ax.set_ylim(0, 105)
    share_ax.set_ylabel("Cells above\nthreshold (%)", fontsize=AXIS_LABEL_SIZE)
    share_ax.spines["top"].set_visible(False)
    share_ax.grid(False)
    format_date_axis(ax)


def plot_temperature_panel(
    ax,
    daily: pd.DataFrame,
    envelope: pd.Series,
    core: pd.Series,
    year: int,
    deg_c: str,
) -> None:
    view = event_view(daily, envelope)
    shade_windows(ax, envelope, core)
    ax.plot(
        view["date"],
        view["mean_tmax_c"],
        color=YEAR_COLORS[year],
        linewidth=2.2,
        marker="o",
        markersize=3.0,
        label="mean daily maximum temperature",
    )
    ax.plot(
        view["date"],
        view["mean_threshold_c"],
        color=THRESHOLD_COLOR,
        linewidth=1.8,
        linestyle="--",
        label="mean threshold",
    )
    ax.text(
        0.01,
        0.93,
        f"{year}: temperature signal",
        transform=ax.transAxes,
        ha="left",
        va="top",
        fontsize=ANNOTATION_SIZE,
        color="#555555",
    )
    ax.grid(True, axis="y", alpha=0.22)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    format_date_axis(ax)


def shade_windows(ax, envelope: pd.Series, core: pd.Series) -> None:
    ax.axvspan(pd.Timestamp(envelope["start"]), pd.Timestamp(envelope["end"]), color=ENVELOPE_COLOR, alpha=0.35)
    ax.axvspan(pd.Timestamp(core["start"]), pd.Timestamp(core["end"]), color=CORE_COLOR, alpha=0.55)


def event_view(daily: pd.DataFrame, envelope: pd.Series) -> pd.DataFrame:
    start = pd.Timestamp(envelope["start"]) - pd.Timedelta(days=3)
    end = pd.Timestamp(envelope["end"]) + pd.Timedelta(days=3)
    return daily[(daily["date"] >= start) & (daily["date"] <= end)].copy()


def event_title(year: int, envelope: pd.Series, core: pd.Series) -> str:
    return (
        f"{year}: {format_period(envelope)} event period, contribution sum "
        f"{float(envelope['regional_hwmid_contribution_sum']):,.0f}\n"
        f"core {format_period(core)}, contribution sum "
        f"{float(core['regional_hwmid_contribution_sum']):,.0f}"
    )


def format_period(row: pd.Series) -> str:
    start = pd.Timestamp(row["start"]).strftime("%d %b")
    end = pd.Timestamp(row["end"]).strftime("%d %b")
    return f"{start}-{end}"


def format_date_axis(ax) -> None:
    ax.xaxis.set_major_locator(mdates.WeekdayLocator(interval=1))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%d %b"))
    ax.tick_params(axis="x", rotation=0)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT_DIR)
    parser.add_argument("--figure-output", type=Path, default=DEFAULT_FIGURE)
    parser.add_argument("--summary-output", type=Path, default=DEFAULT_SUMMARY)
    parser.add_argument("--results-figure-output", type=Path, default=DEFAULT_RESULTS_FIGURE)
    return parser.parse_args()


if __name__ == "__main__":
    main()
