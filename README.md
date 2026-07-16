# Heatwave scenario definition

[![tests](https://github.com/johannesschuhmacher/heatwave_definition/actions/workflows/tests.yml/badge.svg)](https://github.com/johannesschuhmacher/heatwave_definition/actions/workflows/tests.yml)
[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.20793872.svg)](https://doi.org/10.5281/zenodo.20793872)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

This repository identifies heatwave scenario years for energy-system stress
tests. It implements the Heat Wave Magnitude Index daily (HWMId) following
Russo et al. (2015), ranks annual events over configurable country domains and
provides the scripts, derived results and provenance records used by the
associated manuscript.

The versioned Germany-France reference results are:

| Dataset | Rank 1 | HWMId grid-cell sum | Rank 2 | HWMId grid-cell sum |
| --- | ---: | ---: | ---: | ---: |
| E-OBS v33.0e | 2003 | 25,287.00 | 2019 | 10,910.80 |
| ERA5 | 2003 | 24,925.65 | 2026* | 24,441.56 |
| CORDEX-CMIP5 RCP4.5 / IPSL-WRF | 2043 | 30,298.39 | 2070 | 27,049.08 |
| CORDEX-CMIP5 RCP8.5 / MPI-CLM | 2092 | 57,152.09 | 2082 | 50,744.86 |

`2026*` is an incomplete ERA5 current-year result based on data through
1 July 2026. It is an event comparison, not a completed annual ranking.
Absolute grid-cell sums are used to rank years within one data product. They
must not be interpreted as directly comparable physical magnitudes across
products with different grids or spatial coverage.

## Quick start

The no-data demo verifies installation and runs the HWMId calculation on a
small deterministic temperature series.

```text
git clone https://github.com/johannesschuhmacher/heatwave_definition.git
cd heatwave_definition
python -m venv .venv
```

Activate the environment on Linux or macOS:

```bash
source .venv/bin/activate
```

Activate it on Windows PowerShell:

```powershell
.venv\Scripts\Activate.ps1
```

Install and run the checks:

```text
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
python scripts/run_demo.py
python scripts/check_public_release.py
python -m pytest -q
```

The demo writes `outputs/demo/ranked_years_demo.csv` and should rank the two
injected events in 2011 and 2012 first.

## Reproduction levels

### 1. Inspect the published results

No climate data are needed to inspect `results/`. It contains the manuscript
rankings, sensitivity tables, figures and sanitized provenance manifests.
See [results/README.md](results/README.md).

### 2. Run one data product

Copy an example configuration, update its input path and run the package CLI:

```text
python -m heatwave_definition.cli run configs/e_obs.example.toml
python -m heatwave_definition.cli run configs/era5.example.toml
```

The installed `heatwave-definition run <config>` command is equivalent. On
the first country-mask calculation, Cartopy may download the Natural Earth
`admin_0_countries` boundary file. Subsequent runs use Cartopy's local cache.

The dedicated ranking scripts expose additional options:

```text
python scripts/rank_eobs_tx.py <eobs-file> --top-years 20
python scripts/rank_era5_t2m.py <era5-directory> --start-year 1950 --end-year 2026 --top-years 20
python scripts/rank_copernicus_ensembles.py --root <cordex-cmip5-directory> --top-years 20
python scripts/rank_cmip6_tas.py --root <cordex-cmip6-directory> --top-years 10
```

### 3. Rebuild the manuscript snapshot

The complete raw-data-to-results command is:

```text
python scripts/run_complete_climate_workflow.py --eobs-file <eobs-v33-tx.nc> --era5-root <era5-directory> --cmip5-root <cordex-cmip5-directory> --cmip6-root <cordex-cmip6-directory> --tyndp-root <extracted-PEMMDB2-directory>
```

The same paths can be supplied through `HEATWAVE_EOBS_FILE`,
`HEATWAVE_ERA5_ROOT`, `HEATWAVE_CMIP5_ROOT`, `HEATWAVE_CMIP6_ROOT` and
`HEATWAVE_TYNDP_PEMMDB_ROOT`.

`--skip-cmip5`, `--skip-cmip6` and `--reuse-derived-weights` are resume
options. They require the corresponding existing files under `outputs/`; they
are not substitutes for a first complete run.

The workflow performs the following steps:

1. calculate E-OBS and ERA5 historical rankings;
2. automatically select the ERA5 event windows for 2003 and 2026;
3. derive TYNDP 2024 country-capacity weights and rerun all sensitivities;
4. download/cache WorldPop data and calculate population weighting;
5. rank all discovered CORDEX-CMIP5 and CORDEX-CMIP6 chains;
6. regenerate tables, figures and data/software manifests;
7. refresh `results/` and run the public-release check.

The final release command is intentionally data intensive. The archived inputs
used here comprise approximately 0.9 GB E-OBS, 33 GB ERA5, 351 GiB CMIP5 and
2.90 TB CMIP6. Use fast local or network storage and expect the complete run to
take many hours or longer. The demo and unit tests are the appropriate first
check on a laptop.

## Input data

Raw provider data are not redistributed. Exact products, links, variables,
requests, file naming conventions and licences are documented in
[docs/data_download.md](docs/data_download.md). The release snapshot uses:

- E-OBS v33.0e daily maximum temperature, 1950-2025;
- ERA5 hourly 2 m temperature, 1950-2026, converted to daily maximum;
- bias-adjusted CORDEX-CMIP5 3-hourly `tasAdjust`;
- CORDEX-CMIP6 hourly `tas`, converted to daily maximum;
- TYNDP 2024 PEMMDB 2.5 National Trends capacities for 2040;
- WorldPop 2020 1 km UN-adjusted population counts.

Sanitized input inventories are recorded under `results/provenance/` and
`results/cmip6/`. They retain provider file names, sizes and available
integrity information, but no absolute local paths. Raw data, caches and large
metric arrays remain outside Git.

## Method

For every grid cell, the implementation:

1. removes 29 February and uses the standard 365-day HWMId calendar;
2. calculates a calendar-day 90th-percentile threshold from a 31-day moving
   window over 1981-2010;
3. identifies events with at least three consecutive threshold-exceedance days;
4. normalizes daily magnitude using the interquartile range of annual maximum
   temperatures in the reference period;
5. sums daily magnitudes within each event and retains the strongest event per
   grid cell and year;
6. aggregates the annual grid-cell field over the selected spatial domain and
   ranks years by the resulting score.

The reference ranking is an unweighted sum over Germany and France. Alternative
country domains, area-weighted means, population weighting, TYNDP capacity
weighting and alternative ranking criteria are included as sensitivities.
Country masks use Natural Earth administrative boundaries and assign grid cells
by their center coordinates.
Manuscript colors and line styles are defined centrally in
`heatwave_definition/plot_style.py`.

## Interpretation and limitations

- HWMId is dimensionless. A regional grid-cell sum depends on the grid and
  number of included cells; use it for within-product year ranking.
- ERA5 2026 is frozen at the stated cutoff date and remains preliminary until
  the year and source record are complete.
- The ERA5 event-window comparison sums daily contributions from all qualifying
  local events that overlap a selected window. This window score is not the
  annual strongest-event-per-cell score used to rank complete years.
- The CMIP6 run inventory records all discovered groups and explicitly marks
  whether each chain contains the complete HWMId reference period.
- CMIP5 and CMIP6 source variables are sub-daily near-surface air temperature;
  this workflow derives daily maxima before calculating HWMId.
- Country-level TYNDP capacities represent installed capacity, not plant-level
  locations or hourly availability.

Further details on output lineage, computing requirements and release checks
are in [docs/reproducibility.md](docs/reproducibility.md).

## Repository layout

```text
heatwave_definition/  Reusable Python package
configs/              Example TOML configurations
docs/                 Data and reproduction documentation
scripts/              Data processing and publication workflows
tests/                Synthetic regression tests
results/              Versioned tables, figures and provenance
```

## Citation and licence

Use the citation metadata in [CITATION.cff](CITATION.cff) and cite the exact
Zenodo release used in an analysis. The badge above resolves to the concept
DOI and therefore always points to the latest archived version; Zenodo lists
the version-specific DOI on each release page.

The source code is released under the [MIT License](LICENSE). Input datasets
remain subject to their provider licences and acknowledgement requirements.
