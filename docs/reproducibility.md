# Reproducibility guide

## Scope

The repository supports three levels of verification:

1. `python scripts/run_demo.py` checks the HWMId implementation without data.
2. `python -m pytest -q` runs synthetic unit and entry-point tests.
3. `python scripts/run_complete_climate_workflow.py ...` rebuilds the
   manuscript rankings, sensitivities, tables, figures and manifests from raw
   provider inputs.

The first two levels should run on a normal workstation. The third is an HPC or
large-workstation workflow because the available CMIP6 archive alone is about
2.90 TB.

## Software environment

Python 3.11-3.13 is supported. Install `requirements-lock.txt` to reproduce the
tested release environment exactly, or install `.[dev]` to use compatible
newer dependency versions:

```text
python -m pip install -r requirements-lock.txt
python -m pip install -e . --no-deps
```

The environment used to generate the public snapshot is recorded in
`results/provenance/software_environment.csv`.

## Output lineage

```text
raw NetCDF / PEMMDB / WorldPop
        -> daily maximum temperature
        -> grid-cell annual HWMId
        -> spatial and weighted annual scores
        -> ranked scenario years
        -> sensitivities, tables and figures
        -> sanitized results snapshot
```

Intermediate arrays and caches are written below `outputs/` and `data/` and are
ignored by Git. `scripts/snapshot_public_results.py` copies only the curated
artifacts listed in that script to `results/`.

## Release snapshot

- E-OBS: v33.0e, complete years 1950-2025.
- ERA5 completed-year comparison: 1950-2025.
- ERA5 current-year event: data frozen through 1 July 2026.
- CMIP5: eight discovered full-period `tasAdjust` files.
- CMIP6: ten discovered model/experiment groups with unequal end years.
- HWMId reference period: 1981-2010.
- Threshold: calendar-day 90th percentile in a 31-day window.
- Minimum event duration: three consecutive days.
- Reference spatial domain: Germany and France.

## Computing considerations

Approximate release input volumes are 0.9 GB E-OBS, 33 GB ERA5, 351 GiB CMIP5
and 2.90 TB CMIP6. Keep at least enough additional space for daily CMIP6 caches
and intermediate metric arrays. Runtime depends strongly on storage bandwidth;
CMIP6 processing is the dominant step and can take many hours or days.

Use `--cmip6-resume` after an interrupted CMIP6 run. The `--skip-cmip5`,
`--skip-cmip6` and `--reuse-derived-weights` flags reuse existing local outputs
and fail early if those outputs are absent.

## Validation before a release

Run all of the following from a clean checkout:

```text
python scripts/run_demo.py
python scripts/check_public_release.py
python -m compileall -q heatwave_definition scripts tests
python -m pytest -q
```

Then compare the regenerated `results/` tree with the committed snapshot,
inspect all manuscript figures and archive the exact release commit. The raw
input checksums and file inventories should be retained together with the
release DOI.

## Interpretation boundary

The workflow is reproducible independently of a particular climate archive,
but a published scenario year is conditional on data product, model chain,
experiment, spatial domain, reference period and aggregation rule. Absolute
grid-cell HWMId sums are resolution dependent. Compare years within a data
product, and use ranks or explicitly harmonized grids for comparisons across
products.
