# First real PlanetScope pilot

## Objective

Validate acquisition and processing of one Columbia River mouth scene, then expand to 3–5 independently inspected dates. The first result is an optical feature record with traceable inputs. It is not calibrated turbidity, fish abundance, or a complete seasonal model.

## 1. Record the actual ASU entitlement

The ASU request was approved on November 11, 2026. The emailed invitation's 14 days refer to acceptance, not the duration of imagery access. In Planet Account Manager, inspect Overview, Usage, and the available plan/product details. Product validity may require the ASU account administrator's view.

Privately record: account/workspace, enabled PlanetScope scene assets, geographic/date coverage, product access start/end, remaining quota or credits, and the applicable research/publication terms. Do not place account identifiers, invitation links, credentials, or contract screenshots in git. If validity is not visible, ask the ASU administrator for the current access end date and renewal requirements. No permanent, graduation-linked, or Basic Education & Research duration is assumed here.

The ASU approval explicitly requires attribution identifying **Planet Labs PBC** as the source for publications based on its content. The institutional agreement governs retention and redistribution, including after access ends.

## 2. Install and inspect a request plan

Run from the repository root in an isolated environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e . pytest
python -m pytest -q
python -m estuary_intelligence.pilot --start 2026-07-01 --end 2026-08-01 --limit 10 --dry-run --output outputs/planet_pilot_plan.json
```

The end date is exclusive. July 2026 is an initial historical discovery window, not a representative seasonal sample. The existing AOI is a preliminary Columbia mouth bounding polygon, not a validated water-only mask. The dry run makes no network calls and requires no credentials.

## 3. Inspect actual catalog and asset permissions

Use a local key only. This prompt keeps the value out of chat, git and shell history:

```bash
python - <<'PY'
import os
from getpass import getpass
from estuary_intelligence.pilot import main

os.environ['PL_API_KEY'] = getpass('Planet API key (hidden): ')
main(['--start', '2026-07-01', '--end', '2026-08-01',
      '--limit', '10', '--output', 'outputs/planet_pilot.json'])
PY
```

The command performs bounded catalog and asset-metadata requests. It never activates an asset, creates an order, or downloads imagery. API usage and product quota remain governed by the account; this tool does not claim an operation is free.

Read `scenes[].readiness`, asset `download_permission`, and `status` separately. A catalog-visible scene can lack download rights. An inactive permitted asset is not yet downloadable until the provider's activation step. Missing or failed assets are not usable scenes. An empty result is not proof that the whole account is unauthorized.

The manifest keeps exact acquisition timestamps and selected metadata. It excludes signed download URLs, image pixels, and secrets. Treat it as local project evidence until publication permissions are known.

## 4. Select and obtain one scene

Choose a scene that covers the intended study area, has appropriate multispectral surface-reflectance data and aligned UDM2, and is visually suitable over the water. Prefer a consistent sensor/product across dates. `clear_percent` and `cloud_cover` describe the scene, not necessarily the water inside our AOI.

The candidate asset pair is `ortho_analytic_8b_sr` or `ortho_analytic_4b_sr`, plus `ortho_udm2`. Inspect the available raw/processed products and aquatic correction requirements before making physical water-quality claims. Planet's distinct **Analysis-Ready PlanetScope (ARPS)** is explicitly unsuitable for open-water studies.

Download only the selected authorized pilot assets through the account's supported workflow after checking remaining quota. Keep them under ignored `data/raw/`. Save the item ID, full acquisition timestamp, sensor, product, processing details and permissions record. Do not publish raw imagery or signed links.

## 5. Process comparable pixels

Before extraction, clip SR, UDM2 and any independent water mask to the same fixed study geometry and aligned pixel grid. A scene that intersects the search polygon may cover a much larger area; the current extractor reads the full supplied raster. Record coverage and excluded pixels. Do not compare full scenes with different footprints as though they sampled an identical area.

```bash
python -m estuary_intelligence.analyze \
  --surface-reflectance data/raw/SCENE_SR_clipped.tif \
  --udm2 data/raw/SCENE_udm2_clipped.tif \
  --scene-id "$SCENE_ID" \
  --acquired "$ACQUIRED_TIMESTAMP"
```

Set both variables from the real Planet metadata. Do not supply an invented time. The analysis accepts timezone-aware timestamps and records UTC. Each scene receives its own default output directory; an existing output is rejected. For a new processing version, choose new explicit output paths.

Use an independently reviewed binary water mask with `--water-mask` and `--water-mask-mode external` when available. The default NDWI mask is exploratory and may exclude very turbid water. SR, UDM2 and external-mask hashes identify the actual inputs.

## 6. Add environmental context and evaluate

Retrieve NOAA/USGS observations around actual acquisition times using [INSITU_DATA.md](INSITU_DATA.md). Preserve UTC, units, quality flags and gaps. Account for the geographic separation and travel time from upstream gauges. Station observations are environmental context, not pixel-level calibration of offshore sediment.

Inspect the first scene manually before scaling. Require enough independent dates/events before fitting models. Use a simple baseline and hold out dates/events; do not split neighboring pixels randomly. Record cloud, glint, bottom-reflection and atmospheric-correction limits.

## Official references

- [ASU Planet Incubator](https://newspace.asu.edu/planet-asu/)
- [Account validity and invitation acceptance](https://docs.planet.com/platform/get-started/manage-account/)
- [Access dates and usage](https://support.planet.com/hc/en-us/articles/38529169702173-Checking-your-usage-and-remaining-balance)
- [Planet items and assets](https://docs.planet.com/develop/apis/data/items/)
- [Planet item search](https://docs.planet.com/develop/apis/data/item-search/)
- [ARPS open-water limitation, section 5](https://docs.planet.com/data/imagery/arps/techspec/v1-2-0/)
- [Applicable license terms](https://www.planet.com/licensing-information/)
