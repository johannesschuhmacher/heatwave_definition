# Publication checklist

Use this checklist before making the repository public or preparing a release
tag for the scenario-definition paper.

## Repository hygiene

- Keep raw meteorological data, full metric arrays, PDFs, and local debug files
  outside Git.
- Run the public-release check:

```bash
python scripts\check_public_release.py
```

- Inspect `git status --short` before committing. Deletions of previously
  tracked data/output files are expected for a cleanup commit, but the files
  should remain available locally outside the public Git history if they are
  still needed for reruns.

## Reproduction run

- Run the complete publication reproduction workflow:

```bash
python scripts\run_complete_climate_workflow.py
```

- Archive the local run directory outside Git and keep
  `outputs/provenance/*.local.csv` with raw-data paths. Commit only sanitized
  manifests under `results/provenance/`.
- Confirm that `results/rankings/scenario_selection_summary.csv`,
  `results/tables/primary_top10.csv`, `results/ensemble/`, `results/cmip6/`,
  and `results/figures/` were refreshed by the same run.
- Confirm that the generated sensitivity outputs include the Western/Central
  Europe N-1 country masks and the TYNDP 2024 PEMMDB technology-weighted
  rankings, with PV including rooftop PV and pumped hydro separated from
  hydro.
- Confirm that `results/provenance/era5_year_coverage.csv` marks 2026 as an
  incomplete current-year ERA5 file before interpreting 2026 as an event
  comparison.

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
