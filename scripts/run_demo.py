"""Run a small deterministic HWMId example without external climate data."""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from heatwave_definition.hwmid import calc_hwmid
from heatwave_definition.ranking import aggregate_grid_metric


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    dates, tmax = synthetic_temperature()
    latitude = np.array([48.0, 50.0])
    longitude = np.array([2.0, 8.0])

    hwmid, *_ = calc_hwmid(
        tmax,
        latitude,
        longitude,
        dates,
        ref_period=(1981, 2010),
        min_heatwave_days=3,
        threshold_quantile=0.90,
    )
    scores = aggregate_grid_metric(
        latitude,
        longitude,
        hwmid,
        np.ones(hwmid.shape[:2], dtype=bool),
        aggregation="sum",
    )
    years = np.array(sorted(dates.year.unique()), dtype=int)
    order = np.argsort(scores)[::-1]
    ranking = pd.DataFrame(
        {
            "rank": np.arange(1, len(order) + 1),
            "year": years[order],
            "hwmid_sum": scores[order],
        }
    )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    ranking.to_csv(args.output, index=False)
    print(ranking.head(5).to_string(index=False))
    print(f"Wrote demo ranking: {args.output}")


def synthetic_temperature() -> tuple[pd.DatetimeIndex, np.ndarray]:
    dates = pd.date_range("1980-01-01", "2012-12-31", freq="D")
    day = dates.dayofyear.to_numpy()
    year_offset = 0.05 * (dates.year.to_numpy() - 1980)
    baseline = 15.0 + 10.0 * np.sin(2.0 * np.pi * (day - 80) / 365.25) + year_offset
    values = np.broadcast_to(baseline[:, None, None], (len(dates), 2, 2)).copy()

    event_2011 = (dates >= "2011-07-10") & (dates <= "2011-07-17")
    event_2012 = (dates >= "2012-07-20") & (dates <= "2012-07-24")
    values[event_2011, :, :] += 16.0
    values[event_2012, :, :] += 11.0
    return dates, values


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("outputs/demo/ranked_years_demo.csv"),
    )
    return parser.parse_args(argv)


if __name__ == "__main__":
    main()
