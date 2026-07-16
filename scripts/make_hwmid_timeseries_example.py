"""Create a temporal HWMId example figure from one E-OBS grid cell."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import netCDF4 as nc
import numpy as np
import pandas as pd

from heatwave_definition.hwmid import (
    _annual_reference_maxima,
    _build_threshold_masks,
    _find_runs,
    _noleap_day_of_year,
    _noleap_mask,
    _validate_daily_time_axis,
    _validate_hwmid_parameters,
    _validate_reference_period,
)
from heatwave_definition.metrics import load_metrics_file
from heatwave_definition.plot_style import (
    ANNOTATION_SIZE,
    LEGEND_SIZE,
    SECONDARY_TEXT_COLOR,
    SMALL_TEXT_SIZE,
    SUBTITLE_SIZE,
    TEXT_COLOR,
    TITLE_SIZE,
    apply_manuscript_style,
)
from heatwave_definition.regions import classify_countries_matrix


REPO = Path(__file__).resolve().parents[1]
DEFAULT_METRICS = REPO / "outputs" / "raw_metrics" / "metrics_e_obs.npz"
DEFAULT_EOBS = REPO / "data" / "tx_ens_mean_0.25deg_reg_v33.0e.nc"
DEFAULT_OUTPUT = REPO / "outputs" / "figures" / "hwmid_timeseries_example_2003.png"
COUNTRIES = ["Germany", "France"]


@dataclass(frozen=True)
class Event:
    start_idx: int
    end_idx: int
    hwmid: float
    daily_magnitude: np.ndarray
    thresholds: np.ndarray
    t25: float
    t75: float


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    apply_manuscript_style()
    args.output.parent.mkdir(parents=True, exist_ok=True)

    if args.latitude is not None and args.longitude is not None:
        lat_idx, lon_idx, latitude, longitude = nearest_eobs_cell(args.eobs, args.latitude, args.longitude)
    else:
        metrics = load_metrics_file(args.metrics)
        lat_idx, lon_idx = select_example_cell(metrics, args.year)
        latitude = float(metrics.latitude[lat_idx])
        longitude = float(metrics.longitude[lon_idx])
    dates, series = load_eobs_cell(args.eobs, lat_idx, lon_idx)
    noleap_mask = _noleap_mask(dates)
    dates = dates[noleap_mask]
    series = series[noleap_mask]
    events = events_for_year(
        dates=dates,
        series=series,
        year=args.year,
        ref_period=args.ref_period,
        min_heatwave_days=args.min_heatwave_days,
        threshold_quantile=args.threshold_quantile,
    )
    strongest_idx = max(range(len(events)), key=lambda idx: events[idx].hwmid)
    event = events[strongest_idx]
    secondary_events = [
        events[idx]
        for idx in sorted(
            (idx for idx in range(len(events)) if idx != strongest_idx),
            key=lambda idx: events[idx].hwmid,
            reverse=True,
        )
    ]

    figure = build_figure(
        dates=dates,
        series=series,
        latitude=latitude,
        longitude=longitude,
        event=event,
        secondary_events=secondary_events,
        year=args.year,
        min_heatwave_days=args.min_heatwave_days,
        threshold_quantile=args.threshold_quantile,
        ref_period=args.ref_period,
    )
    figure.savefig(args.output, dpi=220)
    plt.close(figure)
    print(args.output)


def select_example_cell(metrics, year: int) -> tuple[int, int]:
    years = np.array(sorted(pd.DatetimeIndex(metrics.dates).year.unique()), dtype=int)
    if year not in set(years):
        raise ValueError(f"Year {year} is not available in {metrics!r}")
    year_idx = int(np.where(years == year)[0][0])
    country_mask = classify_countries_matrix(metrics.latitude, metrics.longitude, COUNTRIES)
    hwmid_year = np.where(country_mask, metrics.hwmid[:, :, year_idx], np.nan)
    if not np.isfinite(hwmid_year).any():
        raise ValueError(f"No finite HWMId values found for {year} inside {COUNTRIES}")
    return tuple(int(value) for value in np.unravel_index(np.nanargmax(hwmid_year), hwmid_year.shape))


def load_eobs_cell(path: Path, lat_idx: int, lon_idx: int) -> tuple[pd.DatetimeIndex, np.ndarray]:
    with nc.Dataset(path, "r") as dataset:
        time_var = dataset.variables["time"]
        decoded = nc.num2date(
            time_var[:],
            units=time_var.units,
            calendar=getattr(time_var, "calendar", "standard"),
            only_use_cftime_datetimes=False,
            only_use_python_datetimes=False,
        )
        dates = pd.DatetimeIndex(pd.to_datetime([value.isoformat() for value in decoded]))
        temp = np.ma.masked_invalid(np.ma.array(dataset.variables["tx"][:, lat_idx, lon_idx], copy=True))
        unit = str(getattr(dataset.variables["tx"], "units", "")).lower()
    series = np.ma.filled(temp, np.nan).astype(float)
    if unit in {"k", "kelvin"}:
        series = series - 273.15
    return dates, series


def nearest_eobs_cell(path: Path, latitude: float, longitude: float) -> tuple[int, int, float, float]:
    with nc.Dataset(path, "r") as dataset:
        lats = np.asarray(dataset.variables["latitude"][:], dtype=float)
        lons = np.asarray(dataset.variables["longitude"][:], dtype=float)
    lat_idx = int(np.nanargmin(np.abs(lats - latitude)))
    lon_idx = int(np.nanargmin(np.abs(lons - longitude)))
    return lat_idx, lon_idx, float(lats[lat_idx]), float(lons[lon_idx])


def events_for_year(
    dates: pd.DatetimeIndex,
    series: np.ndarray,
    year: int,
    ref_period: tuple[int, int],
    min_heatwave_days: int,
    threshold_quantile: float,
) -> list[Event]:
    ref_start, ref_end = ref_period
    _validate_hwmid_parameters(ref_start, ref_end, min_heatwave_days, threshold_quantile)
    _validate_daily_time_axis(dates)
    _validate_reference_period(dates, ref_start, ref_end)
    ref_years = list(range(ref_start, ref_end + 1))
    ref_masks = {
        ref_year: (dates >= pd.Timestamp(ref_year, 1, 1)) & (dates <= pd.Timestamp(ref_year, 12, 31))
        for ref_year in ref_years
    }
    ref_annual_max = _annual_reference_maxima(series, ref_masks)
    t25 = float(np.nanquantile(ref_annual_max, 0.25))
    t75 = float(np.nanquantile(ref_annual_max, 0.75))
    denominator = t75 - t25
    if not np.isfinite(denominator) or denominator <= 0:
        raise ValueError("Reference-period annual maximum-temperature IQR is not positive")

    threshold_masks = _build_threshold_masks(dates, ref_years)
    thresholds = np.array(
        [
            np.nanquantile(series[idx], threshold_quantile)
            if len(idx) and np.isfinite(series[idx]).any()
            else np.nan
            for idx in threshold_masks
        ],
        dtype=float,
    )
    daily_thresholds = thresholds[_noleap_day_of_year(dates) - 1]
    above_threshold = np.isfinite(series) & (series > daily_thresholds)
    runs = _find_runs(above_threshold, min_heatwave_days, dates=dates)

    events: list[Event] = []
    for start_idx, end_idx in runs:
        if int(dates[start_idx].year) != year:
            continue
        event_values = series[start_idx : end_idx + 1]
        daily_magnitude = np.maximum((event_values - t25) / denominator, 0.0)
        events.append(
            Event(
                start_idx=start_idx,
                end_idx=end_idx,
                hwmid=float(np.nansum(daily_magnitude)),
                daily_magnitude=daily_magnitude,
                thresholds=daily_thresholds,
                t25=t25,
                t75=t75,
            )
        )
    if not events:
        raise ValueError(f"No qualifying heatwave event found for {year}")
    return events


def build_figure(
    dates: pd.DatetimeIndex,
    series: np.ndarray,
    latitude: float,
    longitude: float,
    event: Event,
    secondary_events: list[Event],
    year: int,
    min_heatwave_days: int,
    threshold_quantile: float,
    ref_period: tuple[int, int],
) -> plt.Figure:
    secondary_event = secondary_events[0] if secondary_events else None
    first_idx = min([event.start_idx] + ([secondary_event.start_idx] if secondary_event is not None else []))
    last_idx = max([event.end_idx] + ([secondary_event.end_idx] if secondary_event is not None else []))
    window_start = max(np.searchsorted(dates, dates[first_idx] - pd.Timedelta(days=6)), 0)
    window_end = min(np.searchsorted(dates, dates[last_idx] + pd.Timedelta(days=18), side="right"), len(dates))
    window = slice(window_start, window_end)
    event_slice = slice(event.start_idx, event.end_idx + 1)

    fig = plt.figure(figsize=(9.4, 6.2))
    gs = fig.add_gridspec(
        2,
        1,
        height_ratios=[2.3, 1.0],
        left=0.10,
        right=0.97,
        top=0.76,
        bottom=0.12,
        hspace=0.08,
    )
    ax_temp = fig.add_subplot(gs[0, 0])
    ax_mag = fig.add_subplot(gs[1, 0], sharex=ax_temp)

    temp_color = "#172033"
    threshold_color = "#0072B2"
    event_color = "#D55E00"
    magnitude_color = "#B2182B"
    secondary_color = "#8A8F98"

    ax_temp.axvspan(
        dates[event.start_idx],
        dates[event.end_idx] + pd.Timedelta(days=1),
        color=event_color,
        alpha=0.16,
        lw=0,
        label="selected heatwave event",
    )
    if secondary_event is not None:
        ax_temp.axvspan(
            dates[secondary_event.start_idx],
            dates[secondary_event.end_idx] + pd.Timedelta(days=1),
            color=secondary_color,
            alpha=0.13,
            lw=0,
            label="other qualifying event, not retained",
        )
    ax_temp.plot(dates[window], series[window], color=temp_color, lw=1.8, label=r"daily $T_{\max}$")
    ax_temp.plot(
        dates[window],
        event.thresholds[window],
        color=threshold_color,
        lw=1.7,
        ls=(0, (4, 2)),
        label=f"local {int(threshold_quantile * 100)}th-percentile threshold",
    )
    ax_temp.scatter(
        dates[event_slice],
        series[event_slice],
        s=28,
        color=event_color,
        edgecolor="white",
        linewidth=0.6,
        zorder=4,
        label="event days above threshold",
    )
    if secondary_event is not None:
        secondary_slice = slice(secondary_event.start_idx, secondary_event.end_idx + 1)
        ax_temp.scatter(
            dates[secondary_slice],
            series[secondary_slice],
            s=22,
            color=secondary_color,
            edgecolor="white",
            linewidth=0.5,
            zorder=3,
        )
    ax_temp.fill_between(
        dates[event_slice],
        event.thresholds[event_slice],
        series[event_slice],
        where=series[event_slice] > event.thresholds[event_slice],
        color=event_color,
        alpha=0.28,
        linewidth=0,
    )
    if secondary_event is not None:
        secondary_slice = slice(secondary_event.start_idx, secondary_event.end_idx + 1)
        ax_temp.fill_between(
            dates[secondary_slice],
            event.thresholds[secondary_slice],
            series[secondary_slice],
            where=series[secondary_slice] > event.thresholds[secondary_slice],
            color=secondary_color,
            alpha=0.18,
            linewidth=0,
        )
    ax_temp.set_ylabel(r"Daily maximum $T_{\max}$ ($^\circ$C)")
    ax_temp.grid(axis="y", color="#D8D8D8", alpha=0.55, linewidth=0.7)
    ax_temp.spines[["top", "right"]].set_visible(False)
    ax_temp.tick_params(labelbottom=False)

    event_dates = dates[event_slice]
    ax_mag.axvspan(
        dates[event.start_idx],
        dates[event.end_idx] + pd.Timedelta(days=1),
        color=event_color,
        alpha=0.10,
        lw=0,
    )
    ax_mag.bar(
        event_dates,
        event.daily_magnitude,
        color=magnitude_color,
        width=0.80,
        align="center",
        label="daily magnitude contribution",
    )
    if secondary_event is not None:
        secondary_dates = dates[secondary_event.start_idx : secondary_event.end_idx + 1]
        ax_mag.bar(
            secondary_dates,
            secondary_event.daily_magnitude,
            color=secondary_color,
            width=0.80,
            align="center",
        )
    ax_mag.axhline(0, color="#777777", lw=0.8)
    ax_mag.set_ylabel("Daily\nmagnitude")
    ax_mag.set_xlabel("Date")
    ax_mag.grid(axis="y", color="#D8D8D8", alpha=0.55, linewidth=0.7)
    ax_mag.spines[["top", "right"]].set_visible(False)
    ax_mag.xaxis.set_major_locator(mdates.WeekdayLocator(interval=1))
    ax_mag.xaxis.set_major_formatter(mdates.DateFormatter("%d %b"))

    duration = event.end_idx - event.start_idx + 1
    event_label = f"{dates[event.start_idx]:%d %b} to {dates[event.end_idx]:%d %b %Y}"
    ax_temp.text(
        0.99,
        0.05,
        f"{event_label}\n{duration} days; event HWMId = {event.hwmid:.1f}",
        transform=ax_temp.transAxes,
        ha="right",
        va="bottom",
        fontsize=ANNOTATION_SIZE,
        color=TEXT_COLOR,
        bbox={"boxstyle": "round,pad=0.35", "fc": "white", "ec": "#D0D0D0", "alpha": 0.94},
    )
    ax_mag.text(
        0.99,
        0.88,
        rf"daily magnitude = max(($T_{{\max}}-T_{{25}}$)/($T_{{75}}-T_{{25}}$), 0)",
        transform=ax_mag.transAxes,
        ha="right",
        va="top",
        fontsize=SMALL_TEXT_SIZE,
        color=SECONDARY_TEXT_COLOR,
    )
    ax_mag.text(
        0.99,
        0.67,
        rf"$T_{{25}}$ = {event.t25:.1f}$^\circ$C; $T_{{75}}$ = {event.t75:.1f}$^\circ$C",
        transform=ax_mag.transAxes,
        ha="right",
        va="top",
        fontsize=SMALL_TEXT_SIZE,
        color=SECONDARY_TEXT_COLOR,
    )

    fig.suptitle("Temporal construction of an HWMId event", fontsize=TITLE_SIZE, fontweight="bold", y=0.965)
    fig.text(
        0.5,
        0.905,
        (
            f"E-OBS grid cell {latitude:.2f} N, {longitude:.2f} E; {year} example. "
            f"Heatwave days exceed the local threshold for at least {min_heatwave_days} consecutive days; "
            f"daily magnitudes are summed over each event."
        ),
        ha="center",
        va="center",
        fontsize=SUBTITLE_SIZE,
        color=SECONDARY_TEXT_COLOR,
    )
    fig.text(
        0.5,
        0.872,
        (
            f"Threshold: {int(threshold_quantile * 100)}th percentile in a 31-day moving calendar window "
            f"over {ref_period[0]}-{ref_period[1]}."
        ),
        ha="center",
        va="center",
        fontsize=SMALL_TEXT_SIZE,
        color=SECONDARY_TEXT_COLOR,
    )
    handles, labels = ax_temp.get_legend_handles_labels()
    fig.legend(
        handles,
        labels,
        loc="upper center",
        bbox_to_anchor=(0.5, 0.833),
        ncol=3,
        frameon=False,
        fontsize=LEGEND_SIZE,
        columnspacing=1.1,
        handlelength=2.0,
    )
    return fig


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--metrics", type=Path, default=DEFAULT_METRICS)
    parser.add_argument("--eobs", type=Path, default=DEFAULT_EOBS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--year", type=int, default=2003)
    parser.add_argument("--latitude", type=float, help="Optional latitude for a fixed example grid cell.")
    parser.add_argument("--longitude", type=float, help="Optional longitude for a fixed example grid cell.")
    parser.add_argument("--ref-period", type=int, nargs=2, default=(1981, 2010), metavar=("START", "END"))
    parser.add_argument("--min-heatwave-days", type=int, default=3)
    parser.add_argument("--threshold-quantile", type=float, default=0.90)
    return parser.parse_args(argv)


if __name__ == "__main__":
    main()
