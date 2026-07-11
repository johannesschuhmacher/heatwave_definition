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

The scenario selection used for the paper ranks yearly HWMId over grid cells in
Germany and France. The versioned result snapshot selects:

| Dataset | Rank 1 | HWMId sum | Rank 2 | HWMId sum |
| --- | ---: | ---: | ---: | ---: |
| Historical / E-OBS | 2003 | 25,280.48 | 2019 | 10,910.80 |
| Historical / ERA5 | 2003 | 24,902.81 | 2026 | 24,439.57 |
| RCP4.5 / IPSL-WRF | 2043 | 30,300.05 | 2070 | 27,046.41 |
| RCP8.5 / MPI-CLM | 2092 | 56,896.79 | 2082 | 50,706.01 |

The historical E-OBS ranking in the versioned snapshot uses E-OBS v33.0e daily
maximum temperature for 1950-2025. ERA5 is included as a reanalysis-based
historical data-product comparison; the common completed-year comparison with
E-OBS uses 1950-2025, while the 2026 ERA5 file is treated as an incomplete
current-year event comparison. CORDEX-CMIP5 and CORDEX-CMIP6 rankings are
generated from local NetCDF archives and documented in the versioned result
snapshot.

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

The code supports four data families:

- E-OBS daily maximum temperature (`tx`) NetCDF files. The manuscript snapshot
  uses E-OBS v33.0e for 1950-2025.
- ERA5 hourly 2 m temperature (`t2m`) NetCDF files, aggregated internally to
  daily maximum temperature in deg C. The manuscript uses ERA5 as a historical
  comparison to E-OBS and for the current 2026 heatwave event comparison.
- Copernicus/CORDEX-CMIP5 `tasAdjust` 3-hourly NetCDF files, converted
  internally to daily maximum temperature in deg C.
- CORDEX-CMIP6 hourly `tas` NetCDF files, converted internally to daily maximum
  temperature in deg C for ensemble comparison figures.

Download data from the official providers and keep them outside Git, for
example in a local `data/` directory. Before publication, cite and acknowledge
the data providers according to the applicable licences. In particular, E-OBS
data are not bundled here.

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

The complete manuscript workflow is run with:

```bash
python scripts\run_complete_climate_workflow.py ^
  --eobs-file <local-eobs-v33-tx.nc> ^
  --era5-root <local-era5-directory> ^
  --cmip5-root <local-cordex-cmip5-directory> ^
  --cmip6-root <local-cordex-cmip6-directory>
```

On the project machine, the same paths can also be provided through the
environment variables `HEATWAVE_EOBS_FILE`, `HEATWAVE_ERA5_ROOT`,
`HEATWAVE_CMIP5_ROOT`, and `HEATWAVE_CMIP6_ROOT`. The workflow:

- ranks E-OBS v33.0e from daily `tx`;
- ranks ERA5 from annual hourly `t2m` files and writes a year-coverage table;
- selects the 2003 and 2026 ERA5 event windows with the same automatic method;
- ranks all local CORDEX-CMIP5 `tasAdjust` chains and exports the two primary
  manuscript projection rankings from that ensemble table;
- rebuilds the primary CMIP5 sensitivity tables from raw `tasAdjust` files;
- ranks the local CORDEX-CMIP6 archive and updates the climate-data comparison
  figures;
- rebuilds appendix tables, manuscript figures, sanitized provenance files and
  the curated `results/` snapshot;
- runs the public-release check.

The old entry point is kept as an alias:

```bash
python scripts\run_publication_reproduction.py
```

Individual building blocks can still be run for debugging or partial updates.
The most useful ones are:

```bash
python scripts\rank_eobs_tx.py <eobs-v33-tx.nc> --top-years 20
python scripts\rank_era5_t2m.py <era5-directory> --start-year 1950 --end-year 2026 --top-years 20
python scripts\rank_copernicus_ensembles.py --root <cordex-cmip5-directory> --top-years 20
python scripts\rank_cmip6_tas.py --root <cordex-cmip6-directory> --top-years 10
```

Missing ERA5 years can be requested from the Copernicus Climate Data Store after
configuring CDS API credentials:

```bash
python scripts\download_era5_t2m.py --output-dir <local-era5-directory> --start-year 1981 --end-year 2010
```

For TYNDP sensitivity inputs, country weights can be derived from the
ENTSO-E/ENTSOG TYNDP 2024 Scenarios final package, PEMMDB 2.5. Download
`PEMMDB2.zip` from the official TYNDP Scenarios download page, keep it outside
Git, and point the derivation script at the extracted PEMMDB root:

```bash
python scripts\derive_country_weights_from_tyndp2024_pemmdb.py --pemmdb-root "%HEATWAVE_TYNDP_PEMMDB_ROOT%" --year 2040
```

The TYNDP-derived file uses National Trends 2040 PEMMDB market-node capacities
and includes total installed capacity, renewables, and technology-specific
country weights for solar/PV including rooftop PV, wind, hydro excluding pumped
storage, pumped hydro, bio/waste, nuclear, battery storage, battery plus pumped
hydro, and thermal capacity. These weights are country-level sensitivities and
do not represent intra-country plant locations or hourly availability.

Appendix-ready CSV exports and figures are rebuilt by the complete workflow.
They can also be refreshed manually with:

```bash
python scripts\summarize_scenario_selection.py
python scripts\build_appendix_tables.py
python scripts\make_additional_paper_figures.py
python scripts\make_cmip6_internal_figures.py --output-dir outputs\figures
```

Manuscript figure colors, line styles, and categorical heatmap legends are
defined centrally in `heatwave_definition/plot_style.py`.

The derived result snapshot committed with the repository is refreshed from the
local `outputs/` directory with:

```bash
python scripts\snapshot_public_results.py
```

The `results/` directory contains only curated CSV tables and PNG figures.
Provider downloads, raw climate data, local full manifests and large
intermediate arrays remain excluded from Git. Sanitized manifests with file
names, sizes and checksums are stored under `results/provenance/`.

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
