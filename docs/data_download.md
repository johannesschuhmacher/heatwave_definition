# Input data and acquisition

Raw data are kept outside Git. The workflow accepts arbitrary local paths, but
the release results use the products and selections below. Preserve original
file names so that they can be matched against the manifests in `results/`.

## E-OBS

- Provider: Copernicus Climate Change Service / ECA&D.
- Product: E-OBS v33.0e, regular 0.25 degree grid.
- Variable: daily maximum temperature, `tx`, in degrees Celsius.
- Period used: 1950-2025.
- File: `tx_ens_mean_0.25deg_reg_v33.0e.nc`.
- Access: <https://surfobs.climate.copernicus.eu/dataaccess/access_eobs.php>
- Dataset description: Cornes et al. (2018),
  <https://doi.org/10.1029/2017JD028200>.

Place the file at `data/eobs/tx_ens_mean_0.25deg_reg_v33.0e.nc` or pass its
location with `--eobs-file`.

## ERA5

- Provider: Copernicus Climate Change Service / ECMWF.
- Dataset: ERA5 hourly data on single levels.
- Dataset identifier: `reanalysis-era5-single-levels`.
- Variable: `2m_temperature` (`t2m`), all 24 hours.
- Area used: north 71.74, west -12.26, south 32.74, east 36.49.
- Completed comparison period: 1950-2025.
- Current-year event file: 2026 through 1 July 2026 for the archived analysis.
- Access and terms: <https://cds.climate.copernicus.eu/datasets/reanalysis-era5-single-levels>
- Dataset DOI: <https://doi.org/10.24381/cds.adbb2d47>.

Accept the dataset terms and configure the CDS API as described by ECMWF. Then
download one NetCDF file per year:

```text
python scripts/download_era5_t2m.py --output-dir data/era5/t2m_europe --start-year 1950 --end-year 2025
python scripts/download_era5_t2m.py --output-dir data/era5/t2m_europe --start-date 2026-01-01 --end-date 2026-07-01
```

Expected names are `t2m_era5_<year>.nc`. The downloader is resumable and does
not embed credentials in files or command lines.

### ERA5 dewpoint for the humidity-aware sensitivity

- Variable: `2m_dewpoint_temperature` (`d2m`), all 24 hours.
- Area: Germany and France (north 55.25, west -5.50, south 41.25, east 15.50).
- Period: 1980-2026, with 2026 through 1 July 2026.

```text
python scripts/download_era5_dewpoint.py --output-dir data/era5/d2m_de_fr --start-year 1980 --end-year 2026
```

`scripts/extract_era5_dewpoint_subset.py` writes the same `d2m_era5_<year>.nc`
layout from an existing local ERA5 archive.

## NOAA CORe

- Provider: NOAA NCEP Conventional Observation Reanalysis (CORe).
- Variable: ensemble-mean daily maximum 2 m temperature from the daily `flx`
  GRIB files (`TMP:2 m above ground:8@3 hour max`).
- Period used: 1950-2025 and 2026 through 1 July 2026.
- Access: NOAA Open Data Dissemination (NODD) bucket
  <https://storage.googleapis.com/noaa-nws-ncep-core/grib/day/flx>.

```text
python scripts/download_core_t2m_max.py --output-dir data/core --start-date 1950-01-01 --end-date 2026-07-01 --wgrib2 <path-to-wgrib2> --allow-missing
```

The script downloads only the required GRIB message, needs a local `wgrib2`
executable and writes annual `core_t2m_max_europe_<year>.nc` files to
`data/core/europe_netcdf/`. Days missing from the archive are listed in
`missing_days.txt`; for the release snapshot this is only 19 May 2026.

## CORDEX-CMIP5

- Product family: CORDEX-Adjust EUR-25 simulations tailored for the European
  energy sector.
- Variable: bias-adjusted near-surface air temperature, `tasAdjust`.
- Frequency: 3-hourly, converted by this workflow to daily maximum.
- Scenarios used: RCP2.6, RCP4.5 and RCP8.5 where available.
- Bias-adjustment label in the files:
  `IPSL-CDFT22-ERA5-1980-2018`.
- CDS product page: <https://cds.climate.copernicus.eu/datasets/sis-energy-derived-projections>
- Dataset paper: Bartok et al. (2019),
  <https://doi.org/10.1016/j.cliser.2019.100138>.

The ranking script recursively discovers files beginning with `tasAdjust`.
The exact eight files, byte sizes and SHA-256 checksums used for the release
are listed in `results/provenance/raw_input_manifest.csv`.

## CORDEX-CMIP6

- Product family: CORDEX-CMIP6 EUR-12.
- Regional model: ICON-CLM-202407-1-1.
- Driving models ranked for the release: CNRM-ESM2-1 and MPI-ESM1-2-HR.
- Experiments: historical, SSP1-2.6, SSP2-4.5, SSP3-7.0 and SSP5-8.5 where
  available.
- Variable/frequency: hourly point `tas` (`1hrPt`), converted to daily maximum.
- Data access: <https://cordex.org/data-access/cordex-cmip6-data/> and
  <https://esgf-data.dkrz.de/search/cordex-dkrz/>.
- Terms of use: <https://cordex.org/data-access/cordex-cmip6-data/cordex-cmip6-terms-of-use>.

Expected directory hierarchy:

```text
<root>/EUR-12/<institution>/<rcm>/<gcm>/<scenario>/<variant>/<version>/1hrPt/tas/*.nc
```

The processed archive was generated in June 2026 and was labelled in the
NetCDF metadata as CORDEX-CMIP6 output prepared for ESGF within UDAG. At the
time of release, some of these very recent files or tracking handles may not
yet be indexed by all public ESGF nodes. `results/cmip6/` therefore contains a
file-level inventory with relative paths and sizes in addition to the grouped
year-coverage inventory. External raw-data reproduction of those runs depends
on provider publication and availability.

The local archive also contains a single MIROC6 historical file for 1950. The
run inventory records this partial chain, but it is excluded from ranking
because it cannot supply the 1981-2010 HWMId reference period and its boundary
years.

## TYNDP 2024 capacities

- Provider: ENTSO-E and ENTSOG TYNDP 2024 Scenarios.
- Package: PEMMDB 2.5 (`PEMMDB2.zip`).
- Scenario/year used: National Trends 2040.
- Download page: <https://2024.entsos-tyndp-scenarios.eu/download/>.
- Direct package URL used by the derivation script:
  <https://2024-data.entsos-tyndp-scenarios.eu/files/scenarios-inputs/PEMMDB2.zip>.

Extract the archive and pass its root with `--tyndp-root`. The workflow derives
country-level technology weights; it does not infer plant-level locations.

## WorldPop population sensitivity

- Product: WorldPop 2020 1 km UN-adjusted population counts.
- DOI: <https://doi.org/10.5258/SOTON/WP00671>.
- Licence: <https://hub.worldpop.org/data/licence.txt>.

`scripts/sensitivity_population_weighting.py` resolves and downloads the
Germany and France files through the WorldPop API. Files are cached under
`data/worldpop/` and excluded from Git. Exact source URLs and assigned
population totals are recorded in
`results/sensitivity/population_weighting_diagnostics.csv`.

## ISIMIP2b SSP population sensitivity

- Product: ISIMIP2b secondary input data, gridded population 2006-2100,
  0.5 degree, SSP1-SSP5 (`population_ssp<N>soc_0p5deg_annual_2006-2100.nc4`).
- DOI: <https://doi.org/10.48364/ISIMIP.432399>.
- Year used: 2040 for all SSPs.

`scripts/sensitivity_ssp_population_weighting.py` reads the five files from
`--population-dir` and regrids population density to the cached CORDEX-CMIP5
cells. `--grid-file` must be a `tasAdjust` file of the RCP4.5 / IPSL-WRF run.

## Integrity and licences

The local workflow writes path-bearing manifests to `outputs/provenance/`.
Only sanitized manifests are copied to `results/provenance/`. Do not commit
provider files, credentials or local absolute paths. Users are responsible for
accepting provider terms and including the acknowledgements required by each
dataset licence in resulting publications.
