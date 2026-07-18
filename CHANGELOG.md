# Changelog

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
