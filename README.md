# Heatwave scenario definition

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.20793874.svg)](https://doi.org/10.5281/zenodo.20793874)

This repository contains the reproducible code used to identify heatwave
scenario years for energy-system stress testing. The method follows the
Heat Wave Magnitude Index daily (HWMId) approach by Russo et al. (2015):

- daily maximum temperature (`Tmax`)
- reference period 1981-2010
- daily threshold: 90th percentile in a 31-day moving calendar window
- heatwave event: at least three consecutive days above the threshold
- event magnitude: sum of daily magnitudes normalized by the interquartile
  range of annual reference-period maxima

The scenario selection used for the working paper ranks yearly HWMId over
grid cells in Germany and France. With the current local metric files, the
selected years are:

| Dataset | Rank 1 | HWMId sum | Rank 2 | HWMId sum |
| --- | ---: | ---: | ---: | ---: |
| Historical / E-OBS | 2003 | 25,220.98 | 2019 | 10,851.13 |
| RCP4.5 / IPSL-WRF | 2043 | 30,300.04 | 2070 | 27,046.41 |
| RCP8.5 / MPI-CLM | 2092 | 56,896.78 | 2082 | 50,705.97 |

These numbers come from the reproducible `metrics_pickle` reranking workflow
described below. A full raw-NetCDF rerun should be performed once the complete
raw E-OBS and Copernicus/CORDEX files are available in one documented location.

## Repository contents

Source code, configuration examples, tests, and curated derived result tables
and figures are stored in Git. Raw meteorological data, generated metric
arrays, local full-output directories, PDFs, and debug files are intentionally
excluded because of file size and data-licence constraints.

```text
heatwave_definition/      Reusable Python package
configs/                  Example TOML configurations
docs/                     Provenance notes for local data handling
scripts/                  Reproduction helpers for paper tables and figures
tests/                    Lightweight regression tests
results/                  Versioned derived CSV tables and manuscript figures
README.md                 This file
requirements.txt          Runtime dependencies
pyproject.toml            Package metadata and test settings
```

## Data

The code supports two data families:

- E-OBS daily maximum temperature (`tx`) NetCDF files.
- Copernicus/CORDEX `tasAdjust` 3-hourly NetCDF files, converted internally to
  daily maximum temperature in deg C.

Download data from the official providers and keep them outside Git, for
example in a local `data/` directory. Before publication, cite and acknowledge
the data providers according to the applicable licences. In particular, E-OBS
data are not bundled here.

The repository also contains a compatibility mode for the trusted legacy metric
pickles used during the paper cleanup. Those files (`metrics_*.pkl`) are kept
locally, ignored by Git, and must not be published. Pickle files are executable
Python objects; only load metric pickles that were created in this project and
that you trust.

Document local data locations with a local manifest:

```bash
python scripts\write_data_manifest.py --copernicus-root "%HEATWAVE_COPERNICUS_ROOT%"
```

The manifest is written to `outputs/provenance/data_manifest.local.csv` and is
ignored by Git because it contains absolute local paths. See
`docs/data_provenance.md` for the column definitions.

## Installation

Create a fresh environment and install the package in editable mode:

```bash
python -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install -e .
```

Cartopy may require platform-specific binary packages. If pip installation is
problematic on Windows, install the dependencies from conda-forge instead.

## Usage

Copy one of the example configuration files and adapt `input_file` and
`output_dir`:

```bash
copy configs\copernicus_rcp45.example.toml configs\copernicus_rcp45.local.toml
python -m heatwave_definition.cli run configs\copernicus_rcp45.local.toml
```

The run writes:

- `metrics_<run_name>.npz`: HWMId, annual temperature anomaly, heatwave
  duration, threshold, annual Tmax, and start day/index arrays.
- `ranked_years_<run_name>.csv`: scenario-year ranking over the configured
  countries.

The CLI does not write pickles. `npz` output is deterministic, portable, and
safe to inspect without executing arbitrary code.

For the current working-paper update, the full raw Copernicus input was not
available locally for all scenarios. The paper numbers were therefore
recomputed by reranking the existing trusted metric pickles with explicit TOML
configs:

```bash
copy configs\metrics_pickle.example.toml configs\e_obs_metrics.local.toml
copy configs\metrics_pickle.example.toml configs\copernicus_rcp45_metrics.local.toml
copy configs\metrics_pickle.example.toml configs\copernicus_rcp85_metrics.local.toml

python -m heatwave_definition.cli run configs\e_obs_metrics.local.toml
python -m heatwave_definition.cli run configs\copernicus_rcp45_metrics.local.toml
python -m heatwave_definition.cli run configs\copernicus_rcp85_metrics.local.toml
python scripts\summarize_scenario_selection.py
python scripts\make_scenario_figure.py
```

Adapt each `.local.toml` copy before running it. The expected local metric
files are `metrics_e_obs.pkl`, `metrics_copernicus_45.pkl`, and
`metrics_copernicus_85.pkl`.

The local Copernicus2100 raw-data ensemble sensitivity can be reproduced with:

```bash
set HEATWAVE_COPERNICUS_ROOT=<local-path-to-raw-Copernicus2100>
python scripts\rank_copernicus_ensembles.py --scenario rcp45 rcp85
python scripts\summarize_ensemble_rankings.py
```

This workflow reads only the selected country-mask subset from each large
3-hourly NetCDF file. It is intended for scenario-year ranking and does not
write full Europe-wide HWMId arrays.

Country-set and top-N sensitivity checks from the trusted metric pickles can be
run with:

```bash
python scripts\sensitivity_country_sets.py
python scripts\sensitivity_ranking_criteria.py
```

`sensitivity_country_sets.py` writes the Germany-France baseline, Germany-only,
France-only, broader Western/Central European masks, and a Western/Central
Europe N-1 sensitivity where one country is omitted at a time.

The ranking-criteria sensitivity compares the baseline HWMId sum against
area-weighted HWMId mean, unweighted mean HWMId, maximum grid-cell HWMId,
area-weighted heatwave duration, and area-weighted annual Tmax anomaly. It also
writes a compact heatmap to `outputs/figures/`.

Country-weighted checks, for example capacity- or renewable-weighted rankings,
are supported through a CSV with columns `weighting,country,weight`:

```bash
copy configs\country_weights.example.csv configs\country_weights.local.csv
python scripts\sensitivity_country_weights.py --weights configs\country_weights.local.csv
```

Use project-specific installed-capacity or renewable-capacity weights in the
local CSV before interpreting those weighted results.

For TYNDP sensitivity inputs, country weights can be derived from the
ENTSO-E/ENTSOG TYNDP 2024 Scenarios final package, PEMMDB 2.5. Download
`PEMMDB2.zip` from the official TYNDP Scenarios download page, keep it outside
Git, and point the script at the extracted PEMMDB root:

```bash
python scripts\derive_country_weights_from_tyndp2024_pemmdb.py --pemmdb-root "%HEATWAVE_TYNDP_PEMMDB_ROOT%" --year 2040
python scripts\sensitivity_country_weights.py --weights outputs\sensitivity\country_weights_from_tyndp2024_pemmdb_nt2040.csv
```

The TYNDP-derived file uses National Trends 2040 PEMMDB market-node capacities
and includes total installed capacity, renewables, and technology-specific
country weights for solar/PV including rooftop PV, wind, hydro excluding pumped
storage, pumped hydro, bio/waste, nuclear, battery storage, battery plus pumped
hydro, and thermal capacity. These weights are country-level sensitivities and
do not represent intra-country plant locations or hourly availability.

Appendix-ready CSV exports are built with:

```bash
python scripts\build_appendix_tables.py
python scripts\make_additional_paper_figures.py
```

Manuscript figure colors, line styles, and categorical heatmap legends are
defined centrally in `heatwave_definition/plot_style.py`.

The derived result snapshot committed with the repository is refreshed from the
local `outputs/` directory with:

```bash
python scripts\snapshot_public_results.py
```

The `results/` directory contains only curated CSV tables and PNG figures.
Provider downloads, raw climate data, local manifests, trusted pickle files and
large intermediate arrays remain excluded from Git.

## Method notes

The public workflow separates two concepts that were mixed in earlier
exploratory scripts:

- **Grid-cell HWMId**: the paper's scenario ranking is based on yearly HWMId per
  grid cell, summed over selected country masks.
- **Regional mean temperature series**: useful for descriptive time-series
  plots, but not identical to the grid-cell HWMId ranking.

When reporting scenario years, state which criterion was used. For the working
paper scenario definition, use grid-cell HWMId over Germany and France and
report the GCM/RCM model chain together with the emission pathway. The local
ensemble run shows, for example, that IPSL-WRF RCP8.5 ranks 2094/2093 highest,
whereas MPI-CLM RCP8.5 ranks 2092/2082 highest.

## Testing

```bash
python scripts\check_public_release.py
python -m pytest
```

The included tests use synthetic arrays and do not require external NetCDF
files.

## Licence

The code in this repository is released under the MIT License. Input data remain
under their original provider licences.
