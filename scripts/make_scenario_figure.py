"""Create the working-paper HWMId scenario comparison figure."""

from __future__ import annotations

import argparse
from pathlib import Path

import cartopy.crs as ccrs
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from heatwave_definition.metrics import load_metrics_file, resolve_metrics_file
from heatwave_definition.plot_style import (
    AXIS_LABEL_SIZE,
    HWMID_BINS,
    HWMID_CMAP,
    HWMID_NORM,
    PANEL_TITLE_SIZE,
    TITLE_SIZE,
    apply_manuscript_style,
)
from heatwave_definition.ranking import rank_years_by_hwmid


REPO = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = REPO / "outputs" / "figures" / "scenario_hwmid_top2_de_fr.png"
COUNTRIES = ["Germany", "France"]

RUNS = [
    ("Historical", ["metrics_e_obs.npz", "metrics_e_obs.pkl"], "E-OBS"),
    ("RCP4.5", ["metrics_copernicus_rcp45.npz", "metrics_copernicus_45.pkl"], "IPSL-WRF RCP4.5"),
    ("RCP8.5", ["metrics_copernicus_rcp85.npz", "metrics_copernicus_85.pkl"], "MPI-CLM RCP8.5"),
]


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    apply_manuscript_style()
    repo = args.repo.resolve()
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)

    records = []
    for column_title, filenames, run_label in RUNS:
        data = load_metrics_file(resolve_metrics_file(repo, filenames))
        ranking = rank_years_by_hwmid(
            data.latitude,
            data.longitude,
            data.hwmid,
            data.dates,
            no_years=2,
            countries=COUNTRIES,
        )
        years = np.array(sorted(pd.DatetimeIndex(data.dates).year.unique()), dtype=int)
        records.append(
            (column_title, run_label, data.hwmid, data.longitude, data.latitude, years, ranking)
        )

    fig, axes = plt.subplots(
        2,
        3,
        figsize=(13.5, 6.0),
        subplot_kw={"projection": ccrs.PlateCarree()},
        constrained_layout=True,
    )

    mesh = None
    row_labels = ["Rank 1 heatwave", "Rank 2 heatwave"]
    for col, (column_title, run_label, hwmid, lon, lat, years, ranking) in enumerate(records):
        for row in range(2):
            year = int(ranking.iloc[row]["year"])
            year_idx = int(np.where(years == year)[0][0])
            data = hwmid[:, :, year_idx]
            ax = axes[row, col]
            lon2d, lat2d = np.meshgrid(lon, lat)
            mesh = ax.pcolormesh(
                lon2d,
                lat2d,
                data,
                cmap=HWMID_CMAP,
                norm=HWMID_NORM,
                transform=ccrs.PlateCarree(),
            )
            ax.coastlines(linewidth=0.5)
            ax.set_extent([-12, 44, 33, 72], crs=ccrs.PlateCarree())
            ax.set_title(f"{run_label} {year}", fontsize=PANEL_TITLE_SIZE)
            if row == 0:
                ax.text(
                    0.5,
                    1.14,
                    column_title,
                    transform=ax.transAxes,
                    ha="center",
                    va="bottom",
                    fontsize=TITLE_SIZE,
                    fontweight="bold",
                )
            if col == 0:
                ax.text(
                    -0.20,
                    0.5,
                    row_labels[row],
                    transform=ax.transAxes,
                    ha="right",
                    va="center",
                    rotation=90,
                    fontsize=PANEL_TITLE_SIZE,
                    fontweight="bold",
                )

    cbar = fig.colorbar(
        mesh,
        ax=axes,
        orientation="vertical",
        fraction=0.035,
        pad=0.02,
        ticks=HWMID_BINS,
        extend="max",
    )
    cbar.set_label("HWMId (-)", fontsize=AXIS_LABEL_SIZE)
    fig.suptitle(
        "Top heatwave years ranked by summed grid-cell HWMId over Germany and France",
        fontsize=TITLE_SIZE,
    )
    fig.savefig(output, dpi=220)
    print(output)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo",
        type=Path,
        default=REPO,
        help="Directory containing metrics_*.npz files from raw runs, or trusted local legacy pickles.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Output PNG path.",
    )
    return parser.parse_args(argv)


if __name__ == "__main__":
    main()
