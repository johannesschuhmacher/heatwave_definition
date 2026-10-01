# Versioned results

This directory contains a curated snapshot of derived result tables, figures
and sanitized provenance files used by the heatwave scenario-definition
manuscript. Raw meteorological data, local full manifests, provider downloads
and large intermediate arrays are intentionally not included.
Local source paths are stripped from copied tables and manifests; where useful,
only the source file name is retained for provenance.

The files are copied from `outputs/` with:

```bash
python scripts/snapshot_public_results.py
```

Contents:

- `rankings/`: primary scenario-year rankings, including the NOAA CORe comparison product.
- `sensitivity/`: country-mask, weighting, ranking-criterion, population, threshold and
  humidity-metric sensitivity outputs.
- `ensemble/`: Copernicus raw-data ensemble sensitivity summaries.
- `cmip6/`: CORDEX-CMIP6 group/file inventories and top-year rankings.
- `tables/`: appendix-ready compact tables, including the E-OBS/ERA5/NOAA CORe historical data-product comparison.
- `figures/`: manuscript and supplementary figures.
- `validation/`: TYNDP 2024 PEMMDB capacity cross-check tables.
- `provenance/`: sanitized input and software manifests with file names and checksums where available.

Manuscript figures (Climate Services article):

| Figure | File in `figures/` |
| --- | --- |
| 1 | `hwmid_workflow_example_2003.png` |
| 2 | `hwmid_timeseries_example_2003.png` |
| 3 | `climate_data_top10_rank_matrix_with_cmip6.png` |
| 4 | `climate_data_top10_rank_curve_faceted_with_cmip6.png` |
| 5 | `scenario_hwmid_top2_de_fr.png` |
| 6 | `era5_2003_2026_event_period_comparison.png` |
| 7 | `climate_data_heatwave_magnitude_timing_with_cmip6.png` |
| 8 | `country_mask_top2_heatmap.png` |
| 9 | `technology_weighting_top2_heatmap.png` |
| 10 | `ranking_criteria_top2_heatmap_de_fr.png` |
| B.1 | `ssp_population_weighting_top2_heatmap.png` |
| C.1 | `n_minus_1_top2_heatmap.png` |
| D.1 | `era5_humidity_metrics_top10_matrix.png` |
| E.1 | `historical_data_product_top10_matrix_with_core.png` |
| E.2 | `threshold_quantile_sensitivity.png` |

The workflow writes a matching SVG next to each PNG under `outputs/`; only PNG
files are versioned here.
