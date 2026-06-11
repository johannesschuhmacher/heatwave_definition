# Publication checklist

Use this checklist before making the repository public or preparing a release
tag for the scenario-definition paper.

## Repository hygiene

- Keep raw meteorological data, metric arrays, figures, PDFs, and local debug
  files outside Git.
- Keep trusted legacy metric pickles local and ignored by Git.
- Run the public-release check:

```bash
python scripts\check_public_release.py
```

- Inspect `git status --short` before committing. Deletions of previously
  tracked data/output files are expected for a cleanup commit, but the files
  should remain available locally outside the public Git history if they are
  still needed for reruns.

## Reproduction run

- Document local data locations with:

```bash
python scripts\write_data_manifest.py --copernicus-root "%HEATWAVE_COPERNICUS_ROOT%"
```

- Rebuild the primary scenario tables from trusted local metric files:

```bash
python -m heatwave_definition.cli run configs\e_obs_metrics.local.toml
python -m heatwave_definition.cli run configs\copernicus_rcp45_metrics.local.toml
python -m heatwave_definition.cli run configs\copernicus_rcp85_metrics.local.toml
python scripts\summarize_scenario_selection.py
```

- Rebuild sensitivity tables when inputs change:

```bash
python scripts\sensitivity_country_sets.py
python scripts\sensitivity_ranking_criteria.py
python scripts\derive_country_weights_from_tyndp2024_pemmdb.py --pemmdb-root "%HEATWAVE_TYNDP_PEMMDB_ROOT%" --year 2040
python scripts\sensitivity_country_weights.py --weights outputs\sensitivity\country_weights_from_tyndp2024_pemmdb_nt2040.csv
python scripts\build_appendix_tables.py
python scripts\make_additional_paper_figures.py
```

- Confirm that the generated sensitivity outputs include the Western/Central
  Europe N-1 country masks and the TYNDP 2024 PEMMDB technology-weighted
  rankings, with PV including rooftop PV and pumped hydro separated from
  hydro.

## Paper update

- Update the Word papers from the current CSV outputs:

```bash
python scripts\update_paper_with_ensemble_sensitivity.py --paper-dir "<local-paper-directory>"
```

- Report scenario years with both emission pathway and GCM/RCM model chain,
  for example `RCP4.5 / IPSL-WRF / 2043`.
- Before submission, add formal data citations and acknowledgements required by
  E-OBS and Copernicus/CORDEX licences.

## Validation

- Run:

```bash
python -m py_compile $(git ls-files '*.py')
python -m pytest
```

- Render the DOCX papers to PDF/PNG for visual layout QA when LibreOffice is
  available on the machine.
