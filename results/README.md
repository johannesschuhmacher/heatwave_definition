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

- `rankings/`: primary scenario-year rankings.
- `sensitivity/`: country-mask, weighting and ranking-criterion sensitivity outputs.
- `ensemble/`: Copernicus raw-data ensemble sensitivity summaries.
- `cmip6/`: CORDEX-CMIP6 group/file inventories and top-year rankings.
- `tables/`: appendix-ready compact tables, including the E-OBS/ERA5 historical data-product comparison.
- `figures/`: manuscript and supplementary figures.
- `validation/`: TYNDP 2024 PEMMDB capacity cross-check tables.
- `provenance/`: sanitized input and software manifests with file names and checksums where available.
