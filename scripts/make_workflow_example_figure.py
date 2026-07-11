"""Create a visual workflow example figure for the HWMId year ranking."""

from __future__ import annotations

import argparse
from pathlib import Path

import cartopy.crs as ccrs
import cartopy.feature as cfeature
import cartopy.io.shapereader as shpreader
import matplotlib.colors as mcolors
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from heatwave_definition.metrics import load_metrics_file
from heatwave_definition.plot_style import (
    ANNOTATION_SIZE,
    AXIS_LABEL_SIZE,
    HWMID_BINS,
    HWMID_CMAP,
    HWMID_NORM,
    PANEL_TITLE_SIZE,
    SECONDARY_TEXT_COLOR,
    SMALL_TEXT_SIZE,
    SUBTITLE_SIZE,
    TEXT_COLOR,
    TITLE_SIZE,
    apply_manuscript_style,
)
from heatwave_definition.ranking import rank_years_by_hwmid
from heatwave_definition.regions import classify_countries_matrix


REPO = Path(__file__).resolve().parents[1]
DEFAULT_METRICS = REPO / "outputs" / "raw_metrics" / "metrics_e_obs.npz"
DEFAULT_WEIGHTS = REPO / "outputs" / "sensitivity" / "country_weights_from_tyndp2024_pemmdb_nt2040.csv"
DEFAULT_OUTPUT = REPO / "outputs" / "figures" / "hwmid_workflow_example_2003.png"
COUNTRIES = ["Germany", "France"]
EXTENT = [-7.5, 15.5, 41.0, 56.5]
DEFAULT_WEIGHTING = "capacity_tyndp2024_pemmdb_nt2040"


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    apply_manuscript_style()
    args.output.parent.mkdir(parents=True, exist_ok=True)

    data = load_metrics_file(args.metrics)
    years = np.array(sorted(pd.DatetimeIndex(data.dates).year.unique()), dtype=int)
    if args.year not in set(years):
        raise ValueError(f"Year {args.year} is not available in {args.metrics}")
    year_idx = int(np.where(years == args.year)[0][0])

    country_mask = classify_countries_matrix(data.latitude, data.longitude, COUNTRIES)
    country_weights = read_country_weight_shares(args.weights, args.weighting)
    ranking = rank_years_by_hwmid(
        data.latitude,
        data.longitude,
        data.hwmid,
        data.dates,
        no_years=args.top_years,
        countries=COUNTRIES,
    )

    hwmid_year = data.hwmid[:, :, year_idx]
    annual_tmax_year = data.annual_tmax[:, :, year_idx] if data.annual_tmax is not None else None
    score = float(np.nansum(hwmid_year[country_mask]))
    rank = int(ranking.loc[ranking["year"] == args.year, "rank"].iloc[0])

    figure = build_figure(
        longitude=data.longitude,
        latitude=data.latitude,
        annual_tmax_year=annual_tmax_year,
        hwmid_year=hwmid_year,
        country_mask=country_mask,
        country_weights=country_weights,
        ranking=ranking,
        year_count=len(years),
        year=args.year,
        score=score,
        rank=rank,
    )
    figure.savefig(args.output, dpi=220)
    plt.close(figure)
    print(args.output)


def build_figure(
    longitude: np.ndarray,
    latitude: np.ndarray,
    annual_tmax_year: np.ndarray | None,
    hwmid_year: np.ndarray,
    country_mask: np.ndarray,
    country_weights: dict[str, float],
    ranking: pd.DataFrame,
    year_count: int,
    year: int,
    score: float,
    rank: int,
) -> plt.Figure:
    lon2d, lat2d = np.meshgrid(longitude, latitude)
    tmax_bins = [15, 20, 25, 30, 35, 40, 45, 50]
    tmax_cmap = plt.get_cmap("YlOrRd")
    tmax_norm = mcolors.BoundaryNorm(tmax_bins, tmax_cmap.N, extend="both")

    fig = plt.figure(figsize=(12.2, 8.1))
    gs = fig.add_gridspec(
        2,
        3,
        height_ratios=[1.0, 1.0],
        width_ratios=[1.0, 1.0, 1.0],
        left=0.05,
        right=0.96,
        top=0.90,
        bottom=0.12,
        wspace=0.20,
        hspace=0.48,
    )
    map_axes = [
        fig.add_subplot(gs[0, 0], projection=ccrs.PlateCarree()),
        fig.add_subplot(gs[0, 1], projection=ccrs.PlateCarree()),
        fig.add_subplot(gs[0, 2], projection=ccrs.PlateCarree()),
        fig.add_subplot(gs[1, 0], projection=ccrs.PlateCarree()),
    ]
    score_ax = fig.add_subplot(gs[1, 1])
    rank_ax = fig.add_subplot(gs[1, 2])

    if annual_tmax_year is None:
        raise ValueError("annual_tmax is required for the workflow temperature panel")
    tmax_mesh = plot_temperature_map(
        map_axes[0],
        lon2d,
        lat2d,
        annual_tmax_year,
        tmax_cmap,
        tmax_norm,
        title=f"1 Annual maximum temperature ({year})",
    )
    add_horizontal_colorbar(
        fig,
        map_axes[0],
        tmax_mesh,
        "annual maximum daily $T_{\\max}$ ($^\\circ$C)",
        ticks=tmax_bins,
    )

    hwmid_mesh = plot_hwmid_map(
        map_axes[1],
        lon2d,
        lat2d,
        hwmid_year,
        HWMID_CMAP,
        HWMID_NORM,
        country_mask,
        title=f"2 Annual HWMId field ({year})",
        outside_mask=True,
    )
    plot_weight_map(map_axes[2], country_weights)

    masked_hwmid = np.where(country_mask, hwmid_year, np.nan)
    plot_hwmid_map(
        map_axes[3],
        lon2d,
        lat2d,
        masked_hwmid,
        HWMID_CMAP,
        HWMID_NORM,
        country_mask,
        title="",
        outside_mask=True,
    )

    add_horizontal_colorbar(fig, map_axes[1], hwmid_mesh, "HWMId of strongest event", ticks=HWMID_BINS)

    plot_score_panel(score_ax, hwmid_year, country_mask, score, year, rank, year_count)
    plot_ranking_panel(rank_ax, ranking, year)
    fig.suptitle(
        "Example workflow: from gridded heatwave events to a ranked stress-test year",
        fontsize=TITLE_SIZE,
        fontweight="bold",
        y=0.965,
    )
    fig.text(
        0.5,
        0.925,
        "Historical E-OBS example year 2003; annual grid-cell values represent the strongest heatwave event per grid cell.",
        ha="center",
        va="center",
        fontsize=SUBTITLE_SIZE,
        color=SECONDARY_TEXT_COLOR,
    )
    add_aligned_panel_titles(
        fig,
        [
            (map_axes[3], "4 Select Germany and France grid cells"),
            (score_ax, "5 Aggregation"),
            (rank_ax, "6 Rank all years"),
        ],
    )
    return fig


def setup_map(ax) -> None:
    ax.set_extent(EXTENT, crs=ccrs.PlateCarree())
    ax.add_feature(cfeature.LAND, facecolor="#F8F8F5", edgecolor="none", zorder=0)
    ax.add_feature(cfeature.OCEAN, facecolor="#F1F5F8", edgecolor="none", zorder=0)
    ax.coastlines(linewidth=0.5, color="#555555", zorder=4)
    ax.add_feature(cfeature.BORDERS, linewidth=0.4, edgecolor="#666666", zorder=4)
    gl = ax.gridlines(draw_labels=False, linewidth=0.25, color="#CCCCCC", alpha=0.7)
    gl.xlocator = plt.FixedLocator([-5, 0, 5, 10, 15])
    gl.ylocator = plt.FixedLocator([42, 46, 50, 54])


def plot_temperature_map(ax, lon2d, lat2d, values, cmap, norm, title: str):
    setup_map(ax)
    mesh = ax.pcolormesh(
        lon2d,
        lat2d,
        values,
        cmap=cmap,
        norm=norm,
        transform=ccrs.PlateCarree(),
        shading="auto",
        zorder=1,
    )
    if title:
        ax.set_title(title, fontsize=PANEL_TITLE_SIZE, fontweight="bold", pad=8)
    return mesh


def plot_hwmid_map(ax, lon2d, lat2d, values, cmap, norm, country_mask, title: str, outside_mask: bool):
    setup_map(ax)
    mesh = ax.pcolormesh(
        lon2d,
        lat2d,
        values,
        cmap=cmap,
        norm=norm,
        transform=ccrs.PlateCarree(),
        shading="auto",
        zorder=1,
    )
    if not outside_mask:
        outline_country_cells(ax, lon2d, lat2d, country_mask)
    if title:
        ax.set_title(title, fontsize=PANEL_TITLE_SIZE, fontweight="bold", pad=8)
    return mesh


def plot_weight_map(ax, country_weights: dict[str, float]) -> None:
    setup_map(ax)

    cmap = plt.get_cmap("YlGnBu")
    norm = mcolors.Normalize(vmin=0.0, vmax=max(country_weights.values()) * 100.0)
    path = shpreader.natural_earth(resolution="50m", category="cultural", name="admin_0_countries")
    for record in shpreader.Reader(path).records():
        country = str(record.attributes.get("ADMIN", ""))
        share = country_weights.get(country)
        if share is None:
            facecolor = "#F2F2F2"
            edgecolor = "#B8B8B8"
            linewidth = 0.4
            zorder = 1
        else:
            facecolor = cmap(norm(share * 100.0))
            edgecolor = "#172033"
            linewidth = 0.8
            zorder = 3
        ax.add_geometries(
            [record.geometry],
            crs=ccrs.PlateCarree(),
            facecolor=facecolor,
            edgecolor=edgecolor,
            linewidth=linewidth,
            zorder=zorder,
        )

    sm = plt.cm.ScalarMappable(norm=norm, cmap=cmap)
    sm.set_array([])
    add_horizontal_colorbar(plt.gcf(), ax, sm, "share of total TYNDP capacity (%)")
    ax.set_title("3 Optional TYNDP weighting", fontsize=PANEL_TITLE_SIZE, fontweight="bold", pad=8)
    ax.text(
        0.02,
        0.02,
        "Example: total installed capacity",
        transform=ax.transAxes,
        ha="left",
        va="bottom",
        fontsize=SMALL_TEXT_SIZE,
        color="#333333",
        bbox={"boxstyle": "round,pad=0.22", "fc": "white", "ec": "#DADADA", "alpha": 0.90},
    )


def add_horizontal_colorbar(fig, ax, mappable, label: str, ticks=None) -> None:
    cax = ax.inset_axes([0.0, -0.15, 1.0, 0.08])
    cbar = fig.colorbar(mappable, cax=cax, orientation="horizontal", ticks=ticks)
    cbar.set_label(label, fontsize=AXIS_LABEL_SIZE)


def add_aligned_panel_titles(fig, titled_axes, y_pad: float = 0.014) -> None:
    fig.canvas.draw()
    positions = [ax.get_position() for ax, _ in titled_axes]
    title_y = max(position.y1 for position in positions) + y_pad
    for ax, title in titled_axes:
        position = ax.get_position()
        fig.text(
            position.x0 + position.width / 2,
            title_y,
            title,
            ha="center",
            va="bottom",
            fontsize=PANEL_TITLE_SIZE,
            fontweight="bold",
            color=TEXT_COLOR,
        )


def outline_country_cells(ax, lon2d, lat2d, country_mask) -> None:
    ax.contour(
        lon2d,
        lat2d,
        country_mask.astype(float),
        levels=[0.5],
        colors="#172033",
        linewidths=1.0,
        transform=ccrs.PlateCarree(),
        zorder=5,
    )


def plot_score_panel(ax, hwmid_year, country_mask, score: float, year: int, rank: int, year_count: int) -> None:
    selected = hwmid_year[country_mask]
    selected = selected[np.isfinite(selected)]
    positive = selected[selected > 0]

    ax.set_axis_off()
    stats = [
        ("Country cells", f"{int(country_mask.sum()):,}"),
        ("Cells with HWMId > 0", f"{len(positive):,}"),
        (rf"Score $S_{{{year}}}$", f"{score:,.0f}"),
        ("Rank", f"{rank} of {year_count} years"),
    ]
    y = 0.72
    for label, value in stats:
        ax.text(
            0.08,
            y,
            label,
            ha="left",
            va="center",
            fontsize=ANNOTATION_SIZE,
            color=SECONDARY_TEXT_COLOR,
            transform=ax.transAxes,
        )
        ax.text(
            0.92,
            y,
            value,
            ha="right",
            va="center",
            fontsize=AXIS_LABEL_SIZE,
            fontweight="bold",
            color=TEXT_COLOR,
            transform=ax.transAxes,
        )
        ax.plot([0.08, 0.92], [y - 0.047, y - 0.047], color="#E0E0E0", lw=0.8, transform=ax.transAxes)
        y -= 0.115
    ax.text(
        0.5,
        0.045,
        "Optional sensitivities can replace equal grid-cell\nweights with area or country-capacity weights.",
        ha="center",
        va="bottom",
        fontsize=SMALL_TEXT_SIZE,
        color=SECONDARY_TEXT_COLOR,
        wrap=True,
        transform=ax.transAxes,
    )


def plot_ranking_panel(ax, ranking: pd.DataFrame, year: int) -> None:
    top = ranking.head(10).copy()
    colors = ["#D55E00" if int(row.year) == year else "#8FA3B8" for row in top.itertuples()]
    ax.barh(top["rank"], top["hwmid_sum"], color=colors, edgecolor="white", height=0.72)
    ax.invert_yaxis()
    ax.set_xlabel("HWMId sum over Germany and France")
    ax.set_ylabel("Rank")
    ax.set_yticks(top["rank"])
    ax.grid(axis="x", alpha=0.25)
    ax.spines[["top", "right"]].set_visible(False)
    for _, row in top.iterrows():
        ax.text(
            row["hwmid_sum"] + top["hwmid_sum"].max() * 0.015,
            row["rank"],
            str(int(row["year"])),
            va="center",
            ha="left",
            fontsize=ANNOTATION_SIZE,
            fontweight="bold" if int(row["year"]) == year else "normal",
            color=TEXT_COLOR,
        )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--metrics", type=Path, default=DEFAULT_METRICS)
    parser.add_argument("--weights", type=Path, default=DEFAULT_WEIGHTS)
    parser.add_argument("--weighting", default=DEFAULT_WEIGHTING)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--year", type=int, default=2003)
    parser.add_argument("--top-years", type=int, default=10)
    return parser.parse_args(argv)


def read_country_weight_shares(path: Path, weighting: str) -> dict[str, float]:
    table = pd.read_csv(path)
    subset = table[table["weighting"] == weighting].copy()
    if subset.empty:
        raise ValueError(f"No rows found for weighting {weighting!r} in {path}")
    total = float(subset["weight"].sum())
    if total <= 0:
        raise ValueError(f"Weighting {weighting!r} has no positive total capacity")
    return {
        str(row["country"]): float(row["weight"]) / total
        for _, row in subset.iterrows()
        if float(row["weight"]) > 0
    }


if __name__ == "__main__":
    main()
