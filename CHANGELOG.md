# Changelog

## 1.3.0 - 2026-10-01

Code and results for the revised and accepted Climate Services article.

- Added NOAA CORe daily maximum 2 m temperature (download, ranking) and an
  E-OBS/ERA5/CORe comparison for 1950-2025 and with 2026 through 1 July
  (ranks, Spearman correlations, top-ten overlap). Climate-data figures now
  include CORe; CORe uses a secondary axis in the historical rank-curve panel.
- Added a 90th/95th/99th-percentile threshold sensitivity for E-OBS, ERA5 and
  CORe.
- Added an exploratory ERA5 humidity sensitivity (Humidex, Stull wet-bulb
  temperature, no-solar-load WBGT proxy) and ERA5 dewpoint download/extraction.
- Added fixed-2040 ISIMIP2b SSP1-SSP5 population weighting for the primary
  CORDEX-CMIP5 chains; cached CMIP5 cell metrics now store cell longitudes.
- `run_complete_climate_workflow.py` runs these analyses and requires the
  CORe, ERA5 dewpoint, ISIMIP2b population and CMIP5 grid inputs.
- Manuscript figures are written as 450 dpi PNG plus SVG. The results README
  maps each article figure to its file.

## 1.2.1 - 2026-07-18

- Made derived-artifact checksums independent of Windows and Unix line endings
  so the public release validation passes identically in fresh GitHub Actions
  checkouts.

## 1.2.0 - 2026-07-18

- Aligned the HWMId implementation with the standard 365-day calendar by
  excluding 29 February and preserving complete 31-day threshold windows.
- Recomputed all E-OBS, ERA5, CORDEX-CMIP5 and CORDEX-CMIP6 rankings,
  sensitivities, tables and figures from provider data or validated daily
  caches. The selected primary years are unchanged; score values are updated.
- Added a machine-readable HWMId method identifier to rankings and sensitivity
  outputs.
- Added content checksums for E-OBS, ERA5 and CORDEX-CMIP5 inputs, explicit
  name-and-size signatures for the 2.90 TB CMIP6 inventory, and stricter release
  validation.
- Made CMIP6 discovery robust to partially downloaded model chains and record
  their eligibility in the run inventory.
- Removed obsolete pickle compatibility, duplicate import wrappers and an old
  manuscript-editing script.

## 1.1.0 - 2026-07-12

- Recomputed the manuscript snapshot from current E-OBS, ERA5,
  CORDEX-CMIP5 and locally available CORDEX-CMIP6 inputs.
- Added ERA5 2026 current-year event analysis and E-OBS/ERA5 comparison.
- Added CMIP6 ensemble inventories and comparison figures.
- Added population-, capacity-, country-domain- and ranking-criterion
  sensitivity outputs.
- Added a complete publication orchestrator, data provenance manifests,
  a no-data demo, release checks and continuous integration.
- Reworked installation, data acquisition and reproducibility documentation.

## 1.0.0 - 2026-06-22

- First archived release of the HWMId scenario-selection workflow.
