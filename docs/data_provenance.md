# Data provenance

Raw climate data, local configuration files, large intermediate arrays and full
local manifests are intentionally not stored in Git. The complete workflow
writes local inventories under `outputs/provenance/` and sanitized provenance
tables under `results/provenance/`.

The current public snapshot contains sanitized manifests for the E-OBS/ERA5
historical data-product comparison, E-OBS and ERA5 year coverage, and the
primary CMIP5 sensitivity intermediates. Local inventories may additionally
contain absolute paths and must remain outside Git.

Use the final reproduction workflow to regenerate the provenance outputs:

```bash
python scripts\run_complete_climate_workflow.py
```

Typical manifest columns are:

- `role`: raw input, ranking output, sensitivity output, figure, appendix
  table, or versioned result.
- `dataset_family`: provider or local artifact family.
- `scenario`: historical, RCP45, RCP85, or derived.
- `model_chain`: observational dataset or GCM/RCM chain.
- `variable`: climate or derived variable.
- `file_name` and `local_path`: local file reference in the local manifest;
  `local_path` is blank in the sanitized publication manifest.
- `size_bytes`, `sha256`: reproducibility checks.
- `note`: existence or run note.

The older `scripts/write_data_manifest.py` helper is retained for ad hoc local
data inventories, but it is not the final publication manifest.

The current manuscript snapshot uses E-OBS v33.0e daily maximum temperature
for the historical ranking period 1950-2025. ERA5 hourly 2 m temperature is
used as an independent reanalysis-based historical comparison over the completed
common E-OBS/ERA5 period 1950-2025. The ERA5 2026 file is incomplete and is
documented separately as a current-year heatwave event comparison. The
corresponding raw files are kept outside Git; the versioned Git snapshot
contains only derived rankings, comparison tables, figures and checksums.
