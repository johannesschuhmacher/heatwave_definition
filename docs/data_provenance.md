# Data provenance

Raw climate data, trusted legacy metric pickles, generated figures, and ranking
CSVs are intentionally not stored in Git. Use the local manifest script to
document which local files were used for a run:

```bash
python scripts\write_data_manifest.py ^
  --copernicus-root "%HEATWAVE_COPERNICUS_ROOT%" ^
  --eobs-file data\tx_ens_mean_0.25deg_reg_v27.0e.nc ^
  --metrics-file metrics_e_obs.pkl ^
  --metrics-file metrics_copernicus_45.pkl ^
  --metrics-file metrics_copernicus_85.pkl
```

The default output is `outputs/provenance/data_manifest.local.csv`, which is
ignored by Git because it contains absolute local paths. Add `--hash-files` only
when stable file hashes are needed; hashing the full Copernicus NetCDF files can
take a long time.

The manifest columns are:

- `role`: raw input, legacy metric file, or generated output.
- `dataset_family`: provider or local artifact family.
- `scenario`: historical, RCP45, RCP85, or derived.
- `model_chain`: observational dataset or GCM/RCM chain.
- `variable`: climate or derived variable.
- `file_name` and `local_path`: local file reference.
- `exists`, `size_bytes`, `sha256`: local reproducibility checks.
- `source_note`: licence/provenance note for publication review.
