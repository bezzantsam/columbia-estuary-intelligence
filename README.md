# Columbia Estuary Intelligence (CEI)

**Status: research prototype / no Planet imagery downloaded yet.**

A noncommercial research portfolio project initiated by an ASU online Engineering Management graduate student. It studies satellite-observable spatial and temporal changes in the Columbia River estuary and surrounding coastal waters, and asks whether those changes covary with river discharge, tides, and wind.

> This project does **not** predict where fish are, claim to directly measure turbidity in NTU, or infer water quality without calibration. Results from the image-analysis code are **unvalidated reflectance proxies** until independently tested against in-situ observations.

## Project milestone 0 — prepared
- Defined a pilot area of interest (AOI) spanning the Columbia River mouth (see `config/aoi.geojson`). **Preliminary bounding polygon**: refine with a coastline/water polygon prior to results.
- Added a secure PlanetScope catalog search; no imagery orders or quota charges are made.
- Added a local, quality-masked optical image feature extractor for PlanetScope surface-reflectance GeoTIFFs and UDM2 imagery.
- Defined reproducibility, validation, and licensed-data handling rules.
- Added synthetic-fixture unit tests to establish that the basic mechanics work.

## Quick start

Install Python 3.10+ and dependencies:

```bash
python -m pip install -r requirements.txt
python -m pip install -e .
python -m pytest -q
```

### 1. Catalog search (after Planet invitation arrives)

Set the API key **locally** (never in this repository or chat):

```bash
export PL_API_KEY='YOUR_PLANET_API_KEY'
python -m estuary_intelligence.search --start 2026-07-01 --end 2026-08-01 --max-cloud 0.25 --output outputs/planet_catalog.json
```

If your access only supports the Planet web interface, browse/download there and skip automated search. This project does not assume API entitlements until verified.

### 2. Analyze a downloaded PlanetScope surface-reflectance scene

Request **surface reflectance** (4-band or 8-band) and its aligned **UDM2** quality mask. For large scenes, clip at the ordering stage or preprocess consistently using GIS software. Never commit licensed raw imagery.

```bash
python -m estuary_intelligence.analyze \
    --surface-reflectance data/raw/SCENE_AnalyticMS_SR_8b.tif \
    --udm2 data/raw/SCENE_udm2.tif \
    --scene-id YOUR_SCENE_ID \
    --acquired 2026-07-18 \
    --output-csv outputs/scene_features.csv \
    --output-png outputs/scene_preview.png
```

The initial workflow records: eligible clear-pixel fraction, approximate water-pixel fraction (NDWI), median green and red surface reflectance over the detected water mask, and red/green reflectance ratio. They are exploratory features, **not calibrated sediment concentration**. The PNG is an optical-feature visualization, not proof of sediment extent.

**Important:** UDM2 and surface reflectance must have identical pixel shape, CRS, and transforms. Misalignment raises an error instead of silently combining incompatible datasets.

## Core question

*How do patterns of surface reflectance observed near the Columbia River plume vary over time, and how are those variations associated with river discharge and tidal conditions?*

The primary outcome is a set of reproducible optical features and quality masks. A physically meaningful sediment-plume extent or turbidity estimate requires independent labels/calibration and uncertainty assessment.

## Next milestones

1. Verify ASU-specific agreement, product access, rate/quota limits, and attribution restrictions.
2. Select 3–5 cloud-free pilot scenes covering meaningful seasonal and discharge variation; archive only reference IDs and processing metadata in git.
3. Refine water-only AOI, handle cloud/shadow/haze and glint, compare sensors and tide times.
4. Obtain and join relevant USGS hydrology and NOAA CO-OPS water levels, with timestamps and time zones explicit.
5. Establish a simple statistical baseline before any high-capacity AI model; validate against independent observations and out-of-time held-out scenes.
6. Produce an academically appropriate technical report and attribution-compliant figures; request permission before redistribution or commercial use.

## Science limitations

- **Clouds/haze:** Oregon coastal imagery will have substantial coverage gaps.
- **Optics:** Red reflectance and red/green ratio may reflect multiple processes, including suspended sediment, glint, bottom reflectance in shallow water, atmospheric correction artifacts, and sensor differences. They cannot be reported as an NTU measurement without calibration.
- **Water mask:** `(green - NIR)/(green + NIR) > 0` is only an approximate detector and may miss very turbid water. Validate/refine with external shoreline and water-body masks.
- **Sensor differences:** Avoid uncorrected temporal comparisons across 4-band and 8-band products or sensor variants.
- **Study design:** Hold out dates (not random image pixels) when modeling to avoid leakage from near-identical neighboring pixels or times.

## License and publication

ASU's Planet Incubator supplies institutional access, but your **actual account agreement** controls. Planet's general Education & Research terms limit use to **noncommercial research**; data may not be sold or used to develop a product/tool that might be sold. Do not commit raw imagery, account keys, thumbnails, or licensed image exports to a public repository. Check allowable derived-figure publication and required attribution before publishing. See `docs/ACCESS_AND_ETHICS.md`.

## Useful sources
- [ASU Planet Incubator](https://newspace.asu.edu/planet-asu/)
- [Planet Education & Research terms](https://www.planet.com/industries/education-and-research/)
- [PlanetScope SR and bands](https://docs.planet.com/data/imagery/planetscope/)
- [Planet UDM2.1 mask](https://docs.planet.com/data/imagery/udm/)
- [Planet quick search documentation](https://docs.planet.com/develop/apis/data/item-search/)
- [USGS modern water APIs](https://api.waterdata.usgs.gov/)
- [NOAA CO-OPS APIs](https://tidesandcurrents.noaa.gov/web_services_info.html)
