# Modeling roadmap (including advanced models)

The first objective is high-quality and verifiable science, not merely a large model.

## Phase 1 — no ML
- Assemble cloud/shadow/haze and geometry masks using UDM2 and an external land/water shoreline mask.
- Extract calibrated surface-reflectance values; check product scale, band order, georegistration and acquisition times.
- Review suspicious land contamination and glint manually.
- Quantify observation coverage and sampling biases.

## Phase 2 — simple baseline, then time validation
- Compare seasonal and discharge conditions using interpretable statistical models such as linear regression or gradient boosting, depending on the target.
- Connect water-level observations via NOAA CO-OPS, upstream discharge via USGS modern APIs; verify monitoring sites and missing data.
- Hold out entire time windows and dates. Train/test splits across adjacent pixels from the same scene would exaggerate performance.

## Phase 3 — advanced computer vision when suitable labels exist
- A supervised segmentation model (e.g., SegFormer-style transformer or U-Net) can be considered for plume boundaries, **only after expert or independently annotated labels are defined**.
- Compare to a simple water/sediment spectral baseline on exactly the same held-out dates and geographic region.
- Report accuracy, precision/recall, calibration when applicable, sensitivity to cloud masks, cross-sensor transfer, inference cost, uncertainty, and qualitative failure cases.
- A powerful model is not automatically appropriate: pretrained satellite models may expect different spectral bands, radiometric scales, or spatial resolution.

## Scientific guardrail
Until validated, 'NDWI water pixels', 'red surface reflectance', and 'red/green ratio' are only optical features. Never label them directly as sediment concentrations, plume boundaries, or fish habitat.
