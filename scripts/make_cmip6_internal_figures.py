"""Create climate-data comparison figures including CMIP5 and CMIP6 runs."""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.cm import ScalarMappable
from matplotlib.colors import Normalize
from matplotlib.lines import Line2D
from matplotlib.patches import Rectangle
import numpy as np
import pandas as pd

from heatwave_definition.plot_style import (
    AXIS_LABEL_SIZE,
    LEGEND_SIZE,
    PANEL_TITLE_SIZE,
    TEXT_COLOR,
    apply_manuscript_style,
)


REPO = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = REPO / "outputs" / "figures"

GROUP_ORDER = {
    "Historical observations and reanalysis": 0,
    "CORDEX-CMIP5 / RCP projections": 1,
    "CORDEX-CMIP6 / CNRM-driven ICON-CLM": 2,
    "CORDEX-CMIP6 / MPI-driven ICON-CLM": 3,
}

CHAIN_ORDER = {
    "E-OBS": 0,
    "ERA5": 1,
    "CNRM-ALADIN": 10,
    "IPSL-WRF": 11,
    "MPI-CLM": 12,
    "NCC-HIRHAM": 13,
    "CMIP6 CNRM-ICON": 20,
    "CMIP6 MPI-ICON": 30,
}

SCENARIO_ORDER = {
    "HISTORICAL": 0,
    "RCP26": 1,
    "RCP45": 1,
    "RCP85": 2,
    "SSP126": 1,
    "SSP245": 2,
    "SSP370": 3,
    "SSP585": 4,
}

CHAIN_SCENARIO_COLORS = {
    ("E-OBS", "HISTORICAL"): "#232323",
    ("ERA5", "HISTORICAL"): "#6F6F6F",
    ("CNRM-ALADIN", "RCP26"): "#9ACAE1",
    ("CNRM-ALADIN", "RCP85"): "#0072B2",
    ("IPSL-WRF", "RCP45"): "#F2A43A",
    ("IPSL-WRF", "RCP85"): "#D55E00",
    ("MPI-CLM", "RCP45"): "#B07AA1",
    ("MPI-CLM", "RCP85"): "#7B3294",
    ("NCC-HIRHAM", "RCP45"): "#66C2A5",
    ("NCC-HIRHAM", "RCP85"): "#009E73",
    ("CMIP6 CNRM-ICON", "HISTORICAL"): "#1B4F72",
    ("CMIP6 CNRM-ICON", "SSP126"): "#9ACAE1",
    ("CMIP6 CNRM-ICON", "SSP245"): "#4A90C2",
    ("CMIP6 CNRM-ICON", "SSP370"): "#0065A8",
    ("CMIP6 CNRM-ICON", "SSP585"): "#003B73",
    ("CMIP6 MPI-ICON", "HISTORICAL"): "#4A235A",
    ("CMIP6 MPI-ICON", "SSP126"): "#D7B5D8",
    ("CMIP6 MPI-ICON", "SSP245"): "#B07AA1",
    ("CMIP6 MPI-ICON", "SSP370"): "#7B3294",
    ("CMIP6 MPI-ICON", "SSP585"): "#3B0F70",
}

CHAIN_FALLBACK_COLORS = {
    "E-OBS": "#232323",
    "ERA5": "#6F6F6F",
    "CNRM-ALADIN": "#0072B2",
    "IPSL-WRF": "#D55E00",
    "MPI-CLM": "#7B3294",
    "NCC-HIRHAM": "#009E73",
    "CMIP6 CNRM-ICON": "#0065A8",
    "CMIP6 MPI-ICON": "#7B3294",
}

LINESTYLES_BY_SCENARIO = {
    "HISTORICAL": "-",
    "RCP26": (0, (2.2, 1.7)),
    "RCP45": "-",
    "RCP85": (0, (4.0, 2.0)),
    "SSP126": (0, (2.2, 1.7)),
    "SSP245": "-",
    "SSP370": (0, (4.0, 2.0)),
    "SSP585": (0, (6.0, 1.8)),
}

RANK_MARKERS = {1: "o", 2: "^"}
RANK_SIZES = {1: 84, 2: 70}
DEFAULT_RANK_SIZE = 34


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    apply_manuscript_style()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    primary_top10 = pd.read_csv(args.primary_top10)
    copernicus_top_years = pd.read_csv(args.copernicus_top_years)
    cmip6_top = pd.read_csv(args.cmip6_top_years)

    combined_top10 = build_combined_top10(primary_top10, copernicus_top_years, cmip6_top)
    combined_top2 = combined_top10[combined_top10["rank"] <= 2].copy()

    combined_top10.to_csv(args.output_dir / "climate_data_top10_with_cmip6.csv", index=False)
    combined_top2.to_csv(args.output_dir / "climate_data_timing_top2_with_cmip6.csv", index=False)

    paths = [
        plot_internal_top10_lines(
            combined_top10,
            args.output_dir / "climate_data_top10_rank_curve_with_cmip6.png",
        ),
        plot_internal_top10_facets(
            combined_top10,
            args.output_dir / "climate_data_top10_rank_curve_faceted_with_cmip6.png",
        ),
        plot_internal_top10_matrix(
            combined_top10,
            args.output_dir / "climate_data_top10_rank_matrix_with_cmip6.png",
        ),
        plot_internal_timing(
            combined_top2,
            args.output_dir / "climate_data_heatwave_magnitude_timing_with_cmip6.png",
        ),
    ]
    for path in paths:
        print(path)


def build_combined_top10(
    primary_top10: pd.DataFrame,
    copernicus_top_years: pd.DataFrame,
    cmip6_top: pd.DataFrame,
) -> pd.DataFrame:
    historical = primary_top10[primary_top10["dataset"].str.startswith("Historical")].copy()
    historical["data_family"] = "Historical"
    historical["group_label"] = "Historical observations and reanalysis"
    historical["scenario"] = "HISTORICAL"
    historical["gcm"] = ""
    historical["chain_key"] = historical["dataset"].map(lambda value: "E-OBS" if "E-OBS" in value else "ERA5")
    historical["plot_label"] = historical["chain_key"]

    copernicus = copernicus_top_years.copy()
    copernicus["dataset"] = copernicus["ensemble"]
    copernicus["data_family"] = "CORDEX-CMIP5"
    copernicus["group_label"] = "CORDEX-CMIP5 / RCP projections"
    copernicus["scenario"] = copernicus["scenario"].map(normalize_scenario)
    copernicus["gcm"] = copernicus["driving_model"]
    copernicus["chain_key"] = copernicus.apply(copernicus_chain_key, axis=1)
    copernicus["plot_label"] = copernicus.apply(copernicus_plot_label, axis=1)

    cmip6 = cmip6_top.copy()
    cmip6["scenario"] = cmip6["scenario"].map(normalize_scenario)
    cmip6["chain_key"] = cmip6.apply(cmip6_chain_key, axis=1)
    cmip6["group_label"] = cmip6["chain_key"].map(cmip6_group_label)
    cmip6["plot_label"] = cmip6.apply(cmip6_plot_label, axis=1)

    combined = pd.concat(
        [
            historical[combined_columns()],
            copernicus[combined_columns()],
            cmip6[combined_columns()],
        ],
        ignore_index=True,
    )
    combined["rank"] = combined["rank"].astype(int)
    combined["year"] = combined["year"].astype(int)
    combined["hwmid_sum"] = combined["hwmid_sum"].astype(float)
    return sort_combined(combined)


def combined_columns() -> list[str]:
    return [
        "dataset",
        "plot_label",
        "data_family",
        "group_label",
        "scenario",
        "gcm",
        "chain_key",
        "rank",
        "year",
        "hwmid_sum",
        "country_cells",
    ]


def sort_combined(frame: pd.DataFrame) -> pd.DataFrame:
    sorted_frame = frame.copy()
    sorted_frame["_group_order"] = sorted_frame["group_label"].map(GROUP_ORDER).fillna(99).astype(int)
    sorted_frame["_chain_order"] = sorted_frame["chain_key"].map(CHAIN_ORDER).fillna(99).astype(int)
    sorted_frame["_scenario_order"] = sorted_frame["scenario"].map(SCENARIO_ORDER).fillna(99).astype(int)
    sorted_frame = sorted_frame.sort_values(
        ["_group_order", "_chain_order", "_scenario_order", "rank", "plot_label"],
        kind="stable",
    )
    return sorted_frame.drop(columns=["_group_order", "_chain_order", "_scenario_order"]).reset_index(drop=True)


def plot_internal_top10_lines(top10: pd.DataFrame, output: Path) -> Path:
    labels = ordered_labels(top10)
    fig, ax = plt.subplots(figsize=(13.2, 8.3))
    fig.subplots_adjust(left=0.08, right=0.98, top=0.84, bottom=0.34)

    for label in labels:
        group = top10[top10["plot_label"] == label].sort_values("rank")
        first = group.iloc[0]
        color = color_for(first)
        scenario = str(first["scenario"])
        ax.plot(
            group["rank"],
            group["hwmid_sum"],
            linestyle=LINESTYLES_BY_SCENARIO.get(scenario, "-"),
            linewidth=2.0,
            color=color,
            alpha=0.88,
            label=label,
            zorder=2,
        )
        for _, row in group.iterrows():
            rank = int(row["rank"])
            marker = RANK_MARKERS.get(rank, "o")
            marker_size = RANK_SIZES.get(rank, DEFAULT_RANK_SIZE)
            ax.scatter(
                row["rank"],
                row["hwmid_sum"],
                marker=marker,
                s=marker_size,
                color=color,
                edgecolor="white",
                linewidth=0.65,
                zorder=4 if rank <= 2 else 3,
            )
    ax.set_title(
        "Top-10 heatwave-year rankings across historical data and climate projections",
        fontsize=PANEL_TITLE_SIZE + 1.0,
        pad=14,
    )
    ax.set_xlabel("Rank", fontsize=AXIS_LABEL_SIZE)
    ax.set_ylabel("HWMId sum over Germany and France", fontsize=AXIS_LABEL_SIZE)
    ax.set_xticks(range(1, 11))
    ax.grid(axis="y", alpha=0.24)
    ax.spines[["top", "right"]].set_visible(False)

    line_handles, line_labels = ax.get_legend_handles_labels()
    rank_handles = [
        Line2D([0], [0], marker="o", color="black", linestyle="None", label="Rank 1", markersize=6.8),
        Line2D([0], [0], marker="^", color="black", linestyle="None", label="Rank 2", markersize=6.8),
        Line2D([0], [0], marker="o", color="black", linestyle="None", label="Ranks 3-10", markersize=4.8),
    ]
    legend = ax.legend(
        handles=line_handles,
        labels=line_labels,
        frameon=False,
        loc="upper center",
        bbox_to_anchor=(0.5, -0.15),
        fontsize=7.0,
        title="Data product / model chain",
        title_fontsize=7.4,
        borderaxespad=0.0,
        ncol=4,
    )
    ax.add_artist(legend)
    ax.legend(
        handles=rank_handles,
        frameon=False,
        loc="upper center",
        bbox_to_anchor=(0.5, -0.31),
        fontsize=7.0,
        title="Marker",
        title_fontsize=7.4,
        borderaxespad=0.0,
        ncol=3,
    )

    fig.savefig(output, dpi=220)
    plt.close(fig)
    return output


def plot_internal_top10_facets(top10: pd.DataFrame, output: Path) -> Path:
    top10 = top10[top10["rank"].between(1, 10)].copy()
    panel_specs = [
        (
            "Historical data products\nE-OBS and ERA5",
            top10["data_family"].eq("Historical"),
        ),
        (
            "CORDEX-CMIP5 projection chains\nRCP scenarios",
            top10["data_family"].eq("CORDEX-CMIP5"),
        ),
        (
            "CORDEX-CMIP6 CNRM-driven ICON-CLM\nHistorical and SSP scenarios",
            top10["group_label"].eq("CORDEX-CMIP6 / CNRM-driven ICON-CLM"),
        ),
        (
            "CORDEX-CMIP6 MPI-driven ICON-CLM\nHistorical and SSP scenarios",
            top10["group_label"].eq("CORDEX-CMIP6 / MPI-driven ICON-CLM"),
        ),
    ]
    fig, axes = plt.subplots(2, 2, figsize=(11.4, 8.3), sharex=True, sharey=False)
    axes_flat = axes.ravel()
    fig.subplots_adjust(left=0.085, right=0.985, top=0.86, bottom=0.17, wspace=0.20, hspace=0.34)

    for ax, (title, mask) in zip(axes_flat, panel_specs):
        subset = top10[mask].copy()
        draw_rank_curves(ax, subset, show_legend=True)
        ax.set_title(title, fontsize=9.6, pad=8)
        if not subset.empty:
            ax.set_ylim(0, subset["hwmid_sum"].max() * 1.12)

    guide_handles = [
        Line2D([0], [0], marker="o", color="black", linestyle="None", label="Rank 1", markersize=6.6),
        Line2D([0], [0], marker="^", color="black", linestyle="None", label="Rank 2", markersize=6.6),
        Line2D([0], [0], marker="o", color="black", linestyle="None", label="Ranks 3-10", markersize=4.8),
        Line2D([0], [0], color="#333333", linestyle="-", linewidth=2.0, label="Historical / RCP4.5 / SSP2-4.5"),
        Line2D([0], [0], color="#333333", linestyle=(0, (2.2, 1.7)), linewidth=2.0, label="RCP2.6 / SSP1-2.6"),
        Line2D([0], [0], color="#333333", linestyle=(0, (4.0, 2.0)), linewidth=2.0, label="RCP8.5 / SSP3-7.0"),
        Line2D([0], [0], color="#333333", linestyle=(0, (6.0, 1.8)), linewidth=2.0, label="SSP5-8.5"),
    ]
    fig.legend(
        handles=guide_handles,
        frameon=False,
        loc="lower center",
        bbox_to_anchor=(0.5, 0.035),
        fontsize=7.5,
        ncol=4,
    )

    for ax in axes_flat:
        ax.set_xticks(range(1, 11))
        ax.grid(axis="y", alpha=0.22)
        ax.spines[["top", "right"]].set_visible(False)
    for ax in axes[:, 0]:
        ax.set_ylabel("HWMId sum over Germany and France", fontsize=AXIS_LABEL_SIZE)
    for ax in axes[1, :]:
        ax.set_xlabel("Rank", fontsize=AXIS_LABEL_SIZE)

    fig.suptitle(
        "Top-10 heatwave-year rankings by data family",
        fontsize=PANEL_TITLE_SIZE + 1.2,
        y=0.965,
    )
    fig.savefig(output, dpi=220)
    plt.close(fig)
    return output


def draw_rank_curves(ax: plt.Axes, subset: pd.DataFrame, show_legend: bool) -> None:
    if subset.empty:
        ax.text(0.5, 0.5, "No data", transform=ax.transAxes, ha="center", va="center", fontsize=8.0)
        return
    for label in ordered_labels(subset):
        group = subset[subset["plot_label"] == label].sort_values("rank")
        first = group.iloc[0]
        color = color_for(first)
        scenario = str(first["scenario"])
        ax.plot(
            group["rank"],
            group["hwmid_sum"],
            linestyle=LINESTYLES_BY_SCENARIO.get(scenario, "-"),
            linewidth=1.9,
            color=color,
            alpha=0.90,
            label=label,
            zorder=2,
        )
        for _, row in group.iterrows():
            rank = int(row["rank"])
            ax.scatter(
                row["rank"],
                row["hwmid_sum"],
                marker=RANK_MARKERS.get(rank, "o"),
                s=RANK_SIZES.get(rank, DEFAULT_RANK_SIZE),
                color=color,
                edgecolor="white",
                linewidth=0.60,
                zorder=4 if rank <= 2 else 3,
            )
    if show_legend:
        ax.legend(frameon=False, fontsize=6.6, loc="upper right")


def plot_internal_top10_matrix(top10: pd.DataFrame, output: Path) -> Path:
    labels = ordered_labels(top10)
    values = top10.pivot(index="plot_label", columns="rank", values="hwmid_sum").reindex(labels)
    years = top10.pivot(index="plot_label", columns="rank", values="year").reindex(labels)
    ranks = list(range(1, 11))
    values = values.reindex(columns=ranks)
    years = years.reindex(columns=ranks)

    relative_values = values.div(values.max(axis=1), axis=0)

    fig_height = max(7.0, 0.42 * len(labels) + 2.4)
    fig, ax = plt.subplots(figsize=(10.8, fig_height))
    fig.subplots_adjust(left=0.31, right=0.90, top=0.88, bottom=0.10)

    image = ax.imshow(
        relative_values.to_numpy(dtype=float),
        aspect="auto",
        cmap="YlOrRd",
        norm=Normalize(vmin=0.0, vmax=1.0),
        zorder=1,
    )

    for row_idx, label in enumerate(labels):
        row_meta = top10[top10["plot_label"] == label].iloc[0]
        chain_color = chain_color_for(row_meta)
        ax.add_patch(
            Rectangle(
                (-0.82, row_idx - 0.5),
                0.22,
                1.0,
                facecolor=chain_color,
                edgecolor="white",
                linewidth=0.45,
                clip_on=False,
                zorder=3,
            )
        )
        for col_idx, rank in enumerate(ranks):
            year = years.loc[label, rank]
            value = values.loc[label, rank]
            if pd.isna(year) or pd.isna(value):
                continue
            relative_value = float(relative_values.loc[label, rank])
            text_color = "white" if relative_value >= 0.72 else TEXT_COLOR
            ax.text(
                col_idx,
                row_idx - 0.13,
                str(int(year)),
                ha="center",
                va="center",
                fontsize=7.4,
                color=text_color,
                fontweight="bold" if rank <= 2 else "normal",
                zorder=4,
            )
            ax.text(
                col_idx,
                row_idx + 0.17,
                f"({format_index_value(float(value))})",
                ha="center",
                va="center",
                fontsize=5.7,
                color=text_color,
                zorder=4,
            )

    add_group_guides(ax, top10, labels, x_label_position=-0.24)
    ax.set_xticks(np.arange(len(ranks)), [f"{rank}" for rank in ranks])
    ax.set_xlabel("Rank", fontsize=AXIS_LABEL_SIZE)
    ax.set_yticks(np.arange(len(labels)), labels)
    ax.tick_params(axis="y", length=0)
    ax.set_title(
        "Top-10 heatwave-year ranking matrix",
        fontsize=PANEL_TITLE_SIZE + 1.0,
        pad=28,
    )
    ax.text(
        0.5,
        1.02,
        "Cell labels show years and native-grid HWMId sums; colors are normalized to the maximum within each row.",
        transform=ax.transAxes,
        ha="center",
        va="bottom",
        fontsize=8.6,
        color="#555555",
    )
    ax.spines[:].set_visible(False)
    ax.set_xlim(-0.9, len(ranks) - 0.5)

    cbar = fig.colorbar(ScalarMappable(norm=image.norm, cmap=image.cmap), ax=ax, fraction=0.032, pad=0.028)
    cbar.set_label("Relative HWMId within each data product", fontsize=8.2)
    cbar.ax.tick_params(labelsize=7.5)

    fig.savefig(output, dpi=220)
    plt.close(fig)
    return output


def plot_internal_timing(top2: pd.DataFrame, output: Path) -> Path:
    labels = ordered_labels(top2)
    y_positions = {label: idx for idx, label in enumerate(labels)}
    fig_height = max(7.0, 0.46 * len(labels) + 2.4)
    fig, ax = plt.subplots(figsize=(10.9, fig_height))
    fig.subplots_adjust(left=0.31, right=0.96, top=0.87, bottom=0.16)

    add_group_backgrounds(ax, top2, labels)

    for _, row in top2.iterrows():
        rank = int(row["rank"])
        y = y_positions[row["plot_label"]] + (-0.09 if rank == 1 else 0.09)
        color = color_for(row)
        ax.scatter(
            row["year"],
            y,
            s=RANK_SIZES.get(rank, DEFAULT_RANK_SIZE),
            marker=RANK_MARKERS.get(rank, "o"),
            color=color,
            edgecolor="white",
            linewidth=0.75,
            alpha=0.97,
            zorder=4,
        )
        ax.annotate(
            str(int(row["year"])),
            (row["year"], y),
            textcoords="offset points",
            xytext=(6, -10 if rank == 1 else 8),
            va="center",
            fontsize=7.0,
            color=TEXT_COLOR,
            bbox={"boxstyle": "round,pad=0.10", "fc": "white", "ec": "none", "alpha": 0.78},
            zorder=5,
        )

    add_group_guides(ax, top2, labels, x_label_position=-0.24)
    ax.set_title(
        "Selected heatwave years across historical data and climate-projection chains",
        fontsize=PANEL_TITLE_SIZE + 1.0,
        pad=28,
    )
    ax.text(
        0.5,
        1.02,
        "Rank 1 and rank 2 selections for Germany and France; colors group model chains and shades distinguish scenarios.",
        transform=ax.transAxes,
        ha="center",
        va="bottom",
        fontsize=8.6,
        color="#555555",
    )
    ax.set_xlabel("Selected year", fontsize=AXIS_LABEL_SIZE)
    ax.set_yticks(np.arange(len(labels)), labels)
    ax.tick_params(axis="y", length=0)
    ax.set_xlim(1948, 2103)
    ax.grid(axis="x", alpha=0.25)
    ax.spines[["top", "right", "left"]].set_visible(False)
    ax.invert_yaxis()

    rank_handles = [
        Line2D([0], [0], marker="o", color="black", linestyle="None", label="Rank 1", markersize=7.0),
        Line2D([0], [0], marker="^", color="black", linestyle="None", label="Rank 2", markersize=7.0),
    ]
    ax.legend(
        handles=rank_handles,
        frameon=False,
        loc="lower center",
        bbox_to_anchor=(0.5, -0.15),
        ncol=2,
        fontsize=LEGEND_SIZE,
    )

    fig.savefig(output, dpi=220)
    plt.close(fig)
    return output


def add_group_backgrounds(ax: plt.Axes, frame: pd.DataFrame, labels: list[str]) -> None:
    bounds = group_bounds(frame, labels)
    for idx, (_group, start, end) in enumerate(bounds):
        if idx % 2 == 1:
            ax.axhspan(start - 0.5, end + 0.5, color="#F7F7F7", zorder=0)


def add_group_guides(ax: plt.Axes, frame: pd.DataFrame, labels: list[str], x_label_position: float) -> None:
    bounds = group_bounds(frame, labels)
    for idx, (group, start, end) in enumerate(bounds):
        if idx > 0:
            ax.plot(
                [x_label_position + 0.01, 1.0],
                [start - 0.5, start - 0.5],
                transform=ax.get_yaxis_transform(),
                color="#9A9A9A",
                linewidth=0.75,
                linestyle=(0, (2.2, 2.4)),
                clip_on=False,
                zorder=2,
            )
        midpoint = (start + end) / 2.0
        ax.text(
            x_label_position,
            midpoint,
            format_group_label(group),
            transform=ax.get_yaxis_transform(),
            ha="right",
            va="center",
            fontsize=8.3,
            color="#404040",
            fontweight="bold",
        )


def group_bounds(frame: pd.DataFrame, labels: list[str]) -> list[tuple[str, int, int]]:
    label_to_group = frame.drop_duplicates("plot_label").set_index("plot_label")["group_label"].to_dict()
    bounds: list[tuple[str, int, int]] = []
    current_group: str | None = None
    start = 0
    for idx, label in enumerate(labels):
        group = label_to_group[label]
        if current_group is None:
            current_group = group
            start = idx
        elif group != current_group:
            bounds.append((current_group, start, idx - 1))
            current_group = group
            start = idx
    if current_group is not None:
        bounds.append((current_group, start, len(labels) - 1))
    return bounds


def ordered_labels(frame: pd.DataFrame) -> list[str]:
    ordered = sort_combined(frame).drop_duplicates("plot_label")
    return ordered["plot_label"].tolist()


def color_for(row: pd.Series) -> str:
    key = (str(row["chain_key"]), str(row["scenario"]))
    return CHAIN_SCENARIO_COLORS.get(key, chain_color_for(row))


def chain_color_for(row: pd.Series) -> str:
    return CHAIN_FALLBACK_COLORS.get(str(row["chain_key"]), "#666666")


def copernicus_chain_key(row: pd.Series) -> str:
    regional_model = str(row.get("regional_model", ""))
    if "ALADIN" in regional_model:
        return "CNRM-ALADIN"
    if "WRF" in regional_model:
        return "IPSL-WRF"
    if "CCLM" in regional_model or "CLM" in regional_model:
        return "MPI-CLM"
    if "HIRHAM" in regional_model:
        return "NCC-HIRHAM"
    return regional_model or "CORDEX-CMIP5"


def copernicus_plot_label(row: pd.Series) -> str:
    return f"{row['chain_key']} {scenario_label(row['scenario'])}"


def cmip6_chain_key(row: pd.Series) -> str:
    gcm = str(row.get("gcm", ""))
    if "CNRM" in gcm:
        return "CMIP6 CNRM-ICON"
    if "MPI" in gcm:
        return "CMIP6 MPI-ICON"
    return f"CMIP6 {gcm}"


def cmip6_group_label(chain_key: str) -> str:
    if "CNRM" in chain_key:
        return "CORDEX-CMIP6 / CNRM-driven ICON-CLM"
    if "MPI" in chain_key:
        return "CORDEX-CMIP6 / MPI-driven ICON-CLM"
    return "CORDEX-CMIP6 projections"


def cmip6_plot_label(row: pd.Series) -> str:
    short_chain = "CNRM-ICON" if "CNRM" in str(row["chain_key"]) else "MPI-ICON"
    return f"{short_chain} {scenario_label(row['scenario'])}"


def normalize_scenario(value: str) -> str:
    return str(value).replace(".", "").replace("-", "").upper()


def scenario_label(value: str) -> str:
    normalized = normalize_scenario(value)
    labels = {
        "HISTORICAL": "Historical",
        "RCP45": "RCP4.5",
        "RCP26": "RCP2.6",
        "RCP85": "RCP8.5",
        "SSP126": "SSP1-2.6",
        "SSP245": "SSP2-4.5",
        "SSP370": "SSP3-7.0",
        "SSP585": "SSP5-8.5",
    }
    return labels.get(normalized, str(value))


def format_group_label(value: str) -> str:
    labels = {
        "Historical observations and reanalysis": "Historical\nobservations\nand reanalysis",
        "CORDEX-CMIP5 / RCP projections": "CORDEX-CMIP5\nRCP projections",
        "CORDEX-CMIP6 / CNRM-driven ICON-CLM": "CORDEX-CMIP6\nCNRM-driven\nICON-CLM",
        "CORDEX-CMIP6 / MPI-driven ICON-CLM": "CORDEX-CMIP6\nMPI-driven\nICON-CLM",
    }
    return labels.get(value, value.replace(" / ", "\n"))


def format_index_value(value: float) -> str:
    if value >= 100_000:
        return f"{value / 1_000:.0f}k"
    if value >= 1_000:
        return f"{value / 1_000:.1f}k"
    return f"{value:.0f}"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--primary-top10", type=Path, default=REPO / "outputs" / "appendix" / "primary_top10.csv")
    parser.add_argument(
        "--copernicus-top-years",
        type=Path,
        default=REPO / "outputs" / "ensemble_rankings" / "copernicus2100_de_fr_top_years.csv",
    )
    parser.add_argument(
        "--cmip6-top-years",
        type=Path,
        default=REPO / "outputs" / "cmip6_internal" / "cmip6_de_fr_top_years.csv",
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser.parse_args(argv)


if __name__ == "__main__":
    main()
