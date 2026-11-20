# Pilot status: November 20, 2026

## Starting point

- Repository inspected at `fc5a074a5fa5dce0878236e047ce285d80881d48`.
- ASU Planet approval received November 11, 2026.
- User reports access is available. The research workspace has no authenticated Planet API key; its browser opens the Planet sign-in screen.
- Account-specific product access, quota and expiry remain unverified. Invitation acceptance and product expiration are separate.
- No real Planet imagery has been downloaded or analyzed in this work session. No plume measurements or model results are claimed.

## Implemented continuation

- Bounded pilot request plan and catalog/asset permission inspection.
- Correct Planet item-type metadata and complete truncation reporting.
- Full timezone-aware acquisition timestamps for subsequent tide matching.
- Separate per-scene outputs and input provenance, including an external water mask when used.
- A command-line runbook to continue from the same repository.

## Live environmental-source check

Local verification: **65 tests passed** on Python 3.12. The pilot dry run completed without a Planet key or network requests, and `git diff --check` passed. These tests verify software behavior with synthetic/mocked inputs, not Planet account entitlement or scientific validity.

The existing clients made live read-only requests on November 20, 2026, for July 1, 2026 (UTC). These checks exercise environmental ingestion; they are not a matched satellite dataset or a scientific result.

| Source | Station/variable | Returned records | Non-null values | Units | Returned UTC span |
| --- | --- | ---: | ---: | --- | --- |
| NOAA CO-OPS | 9439040 / water level, MLLW | 240 | 240 | m | 00:00–23:54 |
| NOAA CO-OPS | 9439040 / wind speed | 24 | 24 | m/s | 00:00–23:00 |
| USGS OGC API | USGS-14246900 / 72137 tidally filtered discharge | 8 | 8 | ft^3/s | 00:00–07:00 |

USGS's returned sample does not cover the full requested day. Preserve that gap; do not fill it or assume a full daily series. All response units and timestamps were preserved. These checks do not establish availability for other dates or independent plume validation.

Reproduce the source check with the existing `estuary_intelligence.insitu` command, `--start 2026-07-01 --end 2026-07-01`, and `--source noaa-water`, `noaa-wind`, or `usgs-tidal-flow`. Output files stay in ignored `outputs/`; no observed imagery or credentials belong in git.

Provider endpoints:

- https://api.tidesandcurrents.noaa.gov/api/prod/datagetter
- https://api.waterdata.usgs.gov/ogcapi/v1/collections/continuous/items

## Next concrete milestone

Authenticate the approved Planet account, record its product validity and remaining allocation, inspect the first candidate list, then download and process one suitable scene with its quality mask. Review the imagery before expanding the pilot or fitting a model.
