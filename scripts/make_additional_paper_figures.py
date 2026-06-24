"""Create additional figures for the heatwave scenario working paper."""

from __future__ import annotations

import argparse
from pathlib import Path
import textwrap

import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
import numpy as np
import pandas as pd

from heatwave_definition.plot_style import (
    DATASET_COLORS,
    DATASET_DISPLAY,
    DATASET_LINESTYLES,
    DATASET_MARKERS,
    DATASET_ORDER,
    STABILITY_BY_CODE,
    STABILITY_CMAP,
    STABILITY_NORM,
    apply_manuscript_style,
    classify_top2_stability,
    stability_legend_handles,
)

REPO = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = REPO / "outputs" / "figures"

WCE_N_MINUS_1_ORDER = [
    "WCE_minus_DE",
    "WCE_minus_FR",
    "WCE_minus_BE",
    "WCE_minus_NL",
    "WCE_minus_LU",
    "WCE_minus_CH",
    "WCE_minus_AT",
    "WCE_minus_IT",
    "WCE_minus_ES",
    "WCE_minus_PL",
    "WCE_minus_CZ",
]
WEIGHTING_ORDER = [
    "capacity_tyndp2024_pemmdb_nt2040",
    "renewables_tyndp2024_pemmdb_nt2040",
    "pv_tyndp2024_pemmdb_nt2040",
    "wind_tyndp2024_pemmdb_nt2040",
    "thermal_nuclear_tyndp2024_pemmdb_nt2040",
    "storage_total_tyndp2024_pemmdb_nt2040",
]


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    apply_manuscript_style()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    top10 = pd.read_csv(args.primary_top10)
    country_mask = pd.read_csv(args.country_mask)
    country_weighted = pd.read_csv(args.country_weighted)
    ensemble = pd.read_csv(args.ensemble_summary)

    paths = [
        plot_top10_rank_curve(top10, args.output_dir / "top10_rank_curve_de_fr.png"),
        plot_country_mask_heatmap(country_mask, args.output_dir / "country_mask_top2_heatmap.png"),
        plot_n_minus_1_heatmap(country_mask, args.output_dir / "n_minus_1_top2_heatmap.png"),
        plot_weighting_heatmap(country_weighted, top10, args.output_dir / "technology_weighting_top2_heatmap.png"),
        plot_ensemble_dotplot(ensemble, args.output_dir / "ensemble_top2_dotplot.png"),
        plot_method_flow(args.output_dir / "method_flow_diagram.png"),
    ]
    for path in paths:
        print(path)


def plot_top10_rank_curve(top10: pd.DataFrame, output: Path) -> Path:
    fig, ax = plt.subplots(figsize=(8.4, 4.6), constrained_layout=True)

    for dataset in DATASET_ORDER:
        group = top10[top10["dataset"] == dataset].sort_values("rank")
        if group.empty:
            continue
        color = DATASET_COLORS[dataset]
        ax.plot(
            group["rank"],
            group["hwmid_sum"],
            marker=DATASET_MARKERS[dataset],
            linestyle=DATASET_LINESTYLES[dataset],
            linewidth=2.2,
            markersize=5.8,
            color=color,
            label=dataset,
        )
        for _, row in group.iterrows():
            ax.annotate(
                str(int(row["year"])),
                (row["rank"], row["hwmid_sum"]),
                textcoords="offset points",
                xytext=(0, 7),
                ha="center",
                fontsize=7,
                color=color,
            )

    ax.set_title("Top-10 heatwave years by summed grid-cell HWMId")
    ax.set_xlabel("Rank")
    ax.set_ylabel("HWMId sum over Germany+France")
    ax.set_xticks(range(1, 11))
    ax.grid(axis="y", alpha=0.25)
    ax.spines[["top", "right"]].set_visible(False)
    ax.legend(frameon=False, loc="upper right")
    fig.savefig(output, dpi=220)
    plt.close(fig)
    return output


def plot_country_mask_heatmap(country_mask: pd.DataFrame, output: Path) -> Path:
    rank1 = country_mask[country_mask["rank"] == 1].pivot(
        index="country_set",
        columns="dataset",
        values="year",
    )
    rank2 = country_mask[country_mask["rank"] == 2].pivot(
        index="country_set",
        columns="dataset",
        values="year",
    )

    mask_order = [
        "DE_FR",
        "DE_only",
        "FR_only",
        "DE_FR_Benelux_Alps",
        "Western_Central_Europe",
    ]
    available_masks = [mask for mask in mask_order if mask in rank1.index]
    available_datasets = [dataset for dataset in DATASET_ORDER if dataset in rank1.columns]
    values = rank1.loc[available_masks, available_datasets].astype(float)

    labels = values.copy().astype(str)
    for row in labels.index:
        for col in labels.columns:
            labels.loc[row, col] = f"{int(rank1.loc[row, col])}\n({int(rank2.loc[row, col])})"

    fig, ax = plt.subplots(figsize=(8.4, 4.8), constrained_layout=True)
    image = ax.imshow(values.to_numpy(), cmap="viridis", aspect="auto")
    ax.set_title("Top-ranked years by country mask (rank 2 in parentheses)")
    ax.set_xticks(np.arange(len(available_datasets)), available_datasets, rotation=20, ha="right")
    ax.set_yticks(np.arange(len(available_masks)), [mask_label(mask) for mask in available_masks])
    ax.tick_params(length=0)

    for row in range(values.shape[0]):
        for col in range(values.shape[1]):
            text_color = heatmap_text_color(values.iloc[row, col], image)
            ax.text(col, row, labels.iloc[row, col], ha="center", va="center", color=text_color, fontsize=8)

    cbar = fig.colorbar(image, ax=ax, shrink=0.82)
    cbar.set_label("Rank-1 year")
    fig.savefig(output, dpi=220)
    plt.close(fig)
    return output


def plot_n_minus_1_heatmap(country_mask: pd.DataFrame, output: Path) -> Path:
    rank1, rank2 = top2_pivots(country_mask, "country_set")
    available_masks = [mask for mask in WCE_N_MINUS_1_ORDER if mask in rank1.index]
    available_datasets = [dataset for dataset in DATASET_ORDER if dataset in rank1.columns]
    values = rank1.loc[available_masks, available_datasets].astype(float)

    labels = values.copy().astype(str)
    for row in labels.index:
        for col in labels.columns:
            labels.loc[row, col] = f"{int(rank1.loc[row, col])}\n({int(rank2.loc[row, col])})"

    fig_height = max(5.0, 0.36 * len(available_masks) + 1.4)
    fig, ax = plt.subplots(figsize=(8.6, fig_height), constrained_layout=True)
    image = ax.imshow(values.to_numpy(), cmap="viridis", aspect="auto")
    ax.set_title("Western/Central Europe N-1 sensitivity (rank 2 in parentheses)")
    ax.set_xticks(np.arange(len(available_datasets)), available_datasets, rotation=20, ha="right")
    ax.set_yticks(np.arange(len(available_masks)), [mask_label(mask) for mask in available_masks])
    ax.tick_params(length=0)

    for row in range(values.shape[0]):
        for col in range(values.shape[1]):
            text_color = heatmap_text_color(values.iloc[row, col], image)
            ax.text(col, row, labels.iloc[row, col], ha="center", va="center", color=text_color, fontsize=8)

    cbar = fig.colorbar(image, ax=ax, shrink=0.84)
    cbar.set_label("Rank-1 year")
    fig.savefig(output, dpi=220)
    plt.close(fig)
    return output


def plot_weighting_heatmap(weighted: pd.DataFrame, primary_top10: pd.DataFrame, output: Path) -> Path:
    rank1, rank2 = top2_pivots(weighted, "weighting")
    available_weightings = [weighting for weighting in WEIGHTING_ORDER if weighting in rank1.index]
    available_datasets = [dataset for dataset in DATASET_ORDER if dataset in rank1.columns]

    reference_rank1 = (
        primary_top10[primary_top10["rank"] == 1]
        .set_index("dataset")["year"]
        .astype(int)
    )
    reference_rank2 = (
        primary_top10[primary_top10["rank"] == 2]
        .set_index("dataset")["year"]
        .astype(int)
    )

    row_labels = ["Unweighted DE+FR reference"] + [weighting_label(weighting) for weighting in available_weightings]
    codes = np.zeros((len(row_labels), len(available_datasets)), dtype=int)
    labels = [["" for _ in available_datasets] for _ in row_labels]

    for col_idx, dataset in enumerate(available_datasets):
        ref_top2 = (int(reference_rank1.loc[dataset]), int(reference_rank2.loc[dataset]))
        labels[0][col_idx] = f"{ref_top2[0]}\n({ref_top2[1]})"
        for row_idx, weighting in enumerate(available_weightings, start=1):
            candidate_top2 = (int(rank1.loc[weighting, dataset]), int(rank2.loc[weighting, dataset]))
            category = classify_top2_stability(ref_top2, candidate_top2)
            codes[row_idx, col_idx] = category.code
            labels[row_idx][col_idx] = f"{candidate_top2[0]}\n({candidate_top2[1]})"

    fig_height = max(4.6, 0.5 * len(row_labels) + 1.8)
    fig, ax = plt.subplots(figsize=(9.2, fig_height))
    ax.imshow(codes, cmap=STABILITY_CMAP, norm=STABILITY_NORM, aspect="auto")
    ax.set_title("TYNDP 2024 capacity-weight sensitivity", fontsize=14, fontweight="bold", pad=16)
    ax.text(
        0.5,
        1.025,
        "Reference: DE+FR, unweighted HWMId sum",
        transform=ax.transAxes,
        ha="center",
        va="bottom",
        fontsize=10,
        color="#5A5A5A",
    )
    ax.set_xticks(np.arange(len(available_datasets)), [DATASET_DISPLAY[dataset] for dataset in available_datasets])
    ax.set_yticks(np.arange(len(row_labels)), row_labels)
    ax.tick_params(length=0)
    ax.set_xticks(np.arange(-0.5, len(available_datasets), 1), minor=True)
    ax.set_yticks(np.arange(-0.5, len(row_labels), 1), minor=True)
    ax.grid(which="minor", color="white", linewidth=1.2)
    ax.tick_params(which="minor", bottom=False, left=False)
    ax.spines[:].set_visible(False)

    for row in range(codes.shape[0]):
        for col in range(codes.shape[1]):
            category = STABILITY_BY_CODE[int(codes[row, col])]
            ax.text(
                col,
                row,
                labels[row][col],
                ha="center",
                va="center",
                color=category.text_color,
                fontsize=8.5,
                fontweight="bold",
            )

    ax.legend(
        handles=stability_legend_handles(),
        frameon=False,
        ncol=2,
        loc="upper center",
        bbox_to_anchor=(0.5, -0.16),
    )
    fig.subplots_adjust(left=0.28, right=0.98, top=0.86, bottom=0.25)
    fig.savefig(output, dpi=220)
    plt.close(fig)
    return output


def top2_pivots(table: pd.DataFrame, index: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    rank1 = table[table["rank"] == 1].pivot(index=index, columns="dataset", values="year")
    rank2 = table[table["rank"] == 2].pivot(index=index, columns="dataset", values="year")
    return rank1, rank2


def heatmap_text_color(value: float, image) -> str:
    red, green, blue, _ = image.cmap(image.norm(value))
    luminance = 0.2126 * red + 0.7152 * green + 0.0722 * blue
    return "black" if luminance > 0.55 else "white"


def plot_ensemble_dotplot(ensemble: pd.DataFrame, output: Path) -> Path:
    top2 = ensemble[ensemble["rank"] <= 2].copy()
    top2["label"] = top2["ensemble"].map(shorten_ensemble_label)
    labels = list(dict.fromkeys(top2["label"]))
    y_positions = {label: idx for idx, label in enumerate(labels)}
    scenario_colors = {"RCP45": "#0072B2", "RCP85": "#D55E00", "RCP4.5": "#0072B2", "RCP8.5": "#D55E00"}
    rank_markers = {1: "o", 2: "^"}

    fig_height = max(4.8, 0.58 * len(labels) + 1.7)
    fig, ax = plt.subplots(figsize=(9.2, fig_height), constrained_layout=True)

    for _, row in top2.iterrows():
        rank = int(row["rank"])
        y = y_positions[row["label"]] + (-0.08 if rank == 1 else 0.08)
        color = scenario_colors.get(str(row["scenario"]), "#4a5568")
        ax.scatter(
            row["year"],
            y,
            s=68 if rank == 1 else 56,
            marker=rank_markers[rank],
            color=color,
            edgecolor="black",
            linewidth=0.4,
            zorder=3,
        )
        label_offset = (6, -11) if rank == 1 else (6, 7)
        ax.annotate(
            str(int(row["year"])),
            (row["year"], y),
            textcoords="offset points",
            xytext=label_offset,
            va="center",
            fontsize=7,
            bbox={"boxstyle": "round,pad=0.12", "fc": "white", "ec": "none", "alpha": 0.75},
        )

    ax.set_title("Copernicus ensemble sensitivity: top heatwave years")
    ax.set_xlabel("Scenario year")
    ax.set_yticks(np.arange(len(labels)), labels)
    ax.set_xlim(2025, 2103)
    ax.grid(axis="x", alpha=0.25)
    ax.spines[["top", "right"]].set_visible(False)
    ax.invert_yaxis()

    legend_handles = [
        Line2D([0], [0], marker="o", color="w", markerfacecolor="#0072B2", markeredgecolor="black", label="RCP4.5 rank 1", markersize=7),
        Line2D([0], [0], marker="^", color="w", markerfacecolor="#0072B2", markeredgecolor="black", label="RCP4.5 rank 2", markersize=7),
        Line2D([0], [0], marker="o", color="w", markerfacecolor="#D55E00", markeredgecolor="black", label="RCP8.5 rank 1", markersize=7),
        Line2D([0], [0], marker="^", color="w", markerfacecolor="#D55E00", markeredgecolor="black", label="RCP8.5 rank 2", markersize=7),
    ]
    ax.legend(handles=legend_handles, frameon=False, ncol=4, loc="lower center", bbox_to_anchor=(0.5, -0.16))
    fig.savefig(output, dpi=220)
    plt.close(fig)
    return output


def plot_method_flow(output: Path) -> Path:
    steps = [
        ("Input data", "E-OBS Tmax\nCopernicus tasAdjust"),
        ("Daily Tmax", "Aggregate 3-hourly values\nto daily maximum"),
        ("HWMId", "90th percentile threshold\n1981-2010 reference"),
        ("Country mask", "Germany+France\nplus sensitivities"),
        ("Year ranking", "Aggregate grid-cell\nannual event scores"),
        ("Scenario years", "Stress-test year\nand sensitivity cases"),
    ]

    fig, ax = plt.subplots(figsize=(8.4, 4.1), constrained_layout=True)
    ax.set_axis_off()

    positions = {
        0: (0.17, 0.72),
        1: (0.50, 0.72),
        2: (0.83, 0.72),
        3: (0.83, 0.34),
        4: (0.50, 0.34),
        5: (0.17, 0.34),
    }
    box_width = 0.24
    box_height = 0.24
    for idx, (title, body) in enumerate(steps):
        x, y = positions[idx]
        rect = plt.Rectangle(
            (x - box_width / 2, y - box_height / 2),
            box_width,
            box_height,
            transform=ax.transAxes,
            facecolor="#edf2f7" if idx < len(steps) - 1 else "#e6fffa",
            edgecolor="#2d3748",
            linewidth=1.0,
        )
        ax.add_patch(rect)
        ax.text(x, y + 0.045, title, transform=ax.transAxes, ha="center", va="center", fontsize=9.5, fontweight="bold")
        ax.text(x, y - 0.055, body, transform=ax.transAxes, ha="center", va="center", fontsize=7.6)
        if idx < len(steps) - 1:
            next_x, next_y = positions[idx + 1]
            ax.annotate(
                "",
                xy=edge_point(x, y, next_x, next_y, box_width, box_height, start=False),
                xytext=edge_point(x, y, next_x, next_y, box_width, box_height, start=True),
                xycoords=ax.transAxes,
                arrowprops={"arrowstyle": "->", "linewidth": 1.2, "color": "#2d3748"},
            )

    ax.text(
        0.5,
        0.08,
        "Baseline criterion: summed grid-cell HWMId over Germany+France; robustness is checked with area weighting, country masks and alternative metrics.",
        transform=ax.transAxes,
        ha="center",
        va="center",
        fontsize=7.5,
        color="#4a5568",
    )
    fig.savefig(output, dpi=220)
    plt.close(fig)
    return output


def edge_point(x1: float, y1: float, x2: float, y2: float, width: float, height: float, start: bool) -> tuple[float, float]:
    x, y = (x1, y1) if start else (x2, y2)
    dx = x2 - x1
    dy = y2 - y1
    if abs(dx) >= abs(dy):
        x += (width / 2 + 0.018) * (1 if dx > 0 else -1) * (1 if start else -1)
    else:
        y += (height / 2 + 0.018) * (1 if dy > 0 else -1) * (1 if start else -1)
    return x, y


def shorten_ensemble_label(label: str) -> str:
    return (
        str(label)
        .replace("CNRM-CERFACS-CNRM-CM5 / CNRM-ALADIN63", "CNRM-CM5 / ALADIN63")
        .replace("IPSL-IPSL-CM5A-MR / IPSL-WRF381P", "IPSL-CM5A-MR / WRF381P")
        .replace("MPI-M-MPI-ESM-LR / CLMcom-CCLM4-8-17", "MPI-ESM-LR / CCLM4-8-17")
        .replace("NCC-NorESM1-M / DMI-HIRHAM5", "NorESM1-M / HIRHAM5")
        .replace(" RCP45", " RCP4.5")
        .replace(" RCP85", " RCP8.5")
    )


def mask_label(label: str) -> str:
    labels = {
        "DE_FR": "DE+FR",
        "DE_only": "DE",
        "FR_only": "FR",
        "DE_FR_Benelux_Alps": "DE+FR+Benelux+Alps",
        "Western_Central_Europe": "Western/Central Europe",
    }
    for code in ["DE", "FR", "BE", "NL", "LU", "CH", "AT", "IT", "ES", "PL", "CZ"]:
        labels[f"WCE_minus_{code}"] = f"WCE minus {code}"
    return labels.get(label, label)


def weighting_label(label: str) -> str:
    return {
        "capacity_tyndp2024_pemmdb_nt2040": "All capacity",
        "renewables_tyndp2024_pemmdb_nt2040": "Renewables",
        "solar_tyndp2024_pemmdb_nt2040": "Solar",
        "pv_tyndp2024_pemmdb_nt2040": "PV incl. rooftop",
        "wind_tyndp2024_pemmdb_nt2040": "Wind",
        "wind_onshore_tyndp2024_pemmdb_nt2040": "Wind onshore",
        "wind_offshore_tyndp2024_pemmdb_nt2040": "Wind offshore",
        "hydro_tyndp2024_pemmdb_nt2040": "Hydro excl. pumped",
        "pumped_hydro_tyndp2024_pemmdb_nt2040": "Pumped hydro",
        "bio_tyndp2024_pemmdb_nt2040": "Bio/waste",
        "nuclear_tyndp2024_pemmdb_nt2040": "Nuclear",
        "storage_tyndp2024_pemmdb_nt2040": "Battery storage",
        "storage_total_tyndp2024_pemmdb_nt2040": "Battery + pumped hydro",
        "thermal_tyndp2024_pemmdb_nt2040": "Thermal",
        "thermal_nuclear_tyndp2024_pemmdb_nt2040": "Thermal + nuclear",
    }.get(label, label)


def wrap_label(label: str, width: int = 28) -> str:
    return "\n".join(textwrap.wrap(label, width=width))


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--primary-top10",
        type=Path,
        default=REPO / "outputs" / "appendix" / "primary_top10.csv",
    )
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
        "--ensemble-summary",
        type=Path,
        default=REPO / "outputs" / "ensemble_rankings" / "copernicus2100_de_fr_top2_summary.csv",
    )
    return parser.parse_args(argv)


if __name__ == "__main__":
    main()
