# Versioned results

This directory contains a curated snapshot of derived result tables and figures
used by the heatwave scenario-definition manuscript. Raw meteorological data,
trusted legacy metric pickles, local data manifests, provider downloads and
large intermediate arrays are intentionally not included.
Local source paths are stripped from copied tables; where useful, only the
source file name is retained for provenance.

The files are copied from `outputs/` with:

```bash
python scripts/snapshot_public_results.py
```

Contents:

- `rankings/`: primary scenario-year rankings.
- `sensitivity/`: country-mask, weighting and ranking-criterion sensitivity outputs.
- `ensemble/`: Copernicus raw-data ensemble sensitivity summaries.
- `tables/`: appendix-ready compact tables.
- `figures/`: manuscript and supplementary figures.
- `validation/`: TYNDP 2024 PEMMDB capacity cross-check tables.
