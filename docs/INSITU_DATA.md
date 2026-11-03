# In-situ environmental data (NOAA CO-OPS + USGS)

This project uses NOAA and USGS station observations to place satellite optical features into environmental context. **These measurements are at monitoring stations, not at the satellite pixel.** Correlation with upstream turbidity is *not* a validation of offshore sediment concentration.

## Selected monitoring sites

- **USGS-14246900**, Columbia River at Port Westward near Quincy, Oregon. Continuous discharge (parameter \`00060\`), tidally filtered discharge (\`72137\`), and turbidity (\`63680\`). USGS identifies turbidity here in **FNU**, and the discharge in **ft³/s**. Check each returned \`unit_of_measure\` before analysis, rather than assuming metric units. The station also has regression-estimated sediment series which are *not* direct sediment samples.
- **NOAA 9439040**, Astoria, Oregon (Tongue Point). Observed water levels, relative to MLLW in the initial client, are reported in **meters**, and wind speed in **m/s** with a direction in degrees. Times are returned in **GMT/UTC**.

Station evidence:
- https://waterdata.usgs.gov/monitoring-location/USGS-14246900/
- https://tidesandcurrents.noaa.gov/stationhome.html?id=9439040
- https://api.waterdata.usgs.gov/docs/ogcapi/
- https://api.tidesandcurrents.noaa.gov/api/dev

## Usage

Install the package and dependencies:

\`\`\`bash
python -m pip install -e . pytest
python -m pytest -q
\`\`\`

Retrieve short windows (inclusive start/end dates; at most 28 days per request):

\`\`\`bash
python -m estuary_intelligence.insitu --source noaa-water --start 2026-07-01 --end 2026-07-07 --output outputs/noaa_water.csv
python -m estuary_intelligence.insitu --source noaa-wind --start 2026-07-01 --end 2026-07-07 --output outputs/noaa_wind.csv
python -m estuary_intelligence.insitu --source usgs-turbidity --start 2026-07-01 --end 2026-07-07 --output outputs/usgs_turbidity.csv
python -m estuary_intelligence.insitu --source usgs-tidal-flow --start 2026-07-01 --end 2026-07-07 --output outputs/usgs_tidal_flow.csv
\`\`\`

USGS accepts an optional API key, set **locally** as \`USGS_API_KEY\`, for applicable rate-limit benefits. Never commit it. No Planet API key is required for these environmental data sources.

## Safety and scientific conventions

1. Keep \`timestamp_utc\` in ISO-8601. NOAA's \`time_zone=gmt\` is UTC; the USGS endpoint provides timezone-qualified timestamps.
2. Data from NOAA water levels have datum **MLLW**. Do not combine with NAVD88, predictions, or another vertical reference without explicitly converting datums.
3. Do not assume all returned records are verified: preserve provisional/approved flags and quality codes.
4. Preserve nulls and gaps instead of interpolating without a documented method.
5. USGS upstream station data can lag the observed offshore surface plume, and tidal stage can complicate flow direction. Plan temporal-lag sensitivity analyses.
6. We have **offline mocked API tests only** so far; live downloads should be validated before claiming the pipeline works end to end.
7. The prototype USGS client paginates by offset. Before large-scale collection, add retry/backoff, cache, resume, and validation against the exact next-page URL returned by USGS, rather than assuming continuous data availability.

## Next experiments

- Confirm a real NOAA water-level and wind response for 9439040.
- Confirm a real USGS parameter response at Port Westward for each selected parameter.
- Record request URL (minus credentials), provider response metadata, observation counts, and gap counts.
- Assemble scene acquisition times, then join to USGS and NOAA over documented lag windows.
- Compare seasonal-baseline and time-held-out model performance; avoid random pixel-level train/test splits.
