# Project Charter | Columbia Estuary Intelligence

## Mission
Develop a reproducible, noncommercial remote-sensing workflow connecting PlanetScope Earth-observation data to hydrological and tidal conditions at the Columbia River mouth.

## Target audience
ASU research mentors, potential NASA/space/semiconductor employers, engineering/program management hiring teams; research claims must be backed by evidence.

## Research question
How does an appropriately quality-masked water-reflectance signal near the Columbia River mouth vary by season and by relevant hydrological drivers?

## Objectives
1. Document all acquired images, quality controls, reprojection/cropping operations, and source timestamps.
2. Calculate exploratory optical features without falsely presenting them as direct turbidity measurements.
3. Validate against independent water observations and compare simple baselines to stronger supervised methods if labels are available.
4. Publish a written research narrative with uncertainty, limitations, and noncommercial license compliance.

## Success criteria
- Reproducible imagery provenance and processing; tests passing.
- At least three independently acquired, usable scene dates and a documented cloud-quality review.
- Evidence-supported time series and plots with missing dates indicated, rather than interpolating false observations.
- Methodological controls and leakage-resistant validation if any predictive model is trained.
- A credible GitHub code portfolio and appropriately attributed report, without exposing licensed raw imagery.

## What is out of scope
- Fish location, catch prediction, navigation advice, or commercial analytics using educationally licensed Planet imagery.
- Concluding suspended-sediment concentration or water quality from uncalibrated pixel values.
- A machine-learning model before realistic independent targets and evaluation design.

## Project management cadence
- Phase 0: research design and toolkit (now).
- Phase 1: access confirmation, scene inventory, quality-controlled pilot imagery.
- Phase 2: NOAA and USGS hydrometeorological data fusion.
- Phase 3: baselines, validation, optional modern vision model; ablation tests.
- Phase 4: report, documented methods, research presentations, job portfolio case study.

## Risks / mitigations
- License prohibits commercial use: keep separate from Reel One production systems and any customer-facing product.
- Cloud gaps: sample multiple dates and disclose missingness.
- Spatial mismatch: mandatory CRS/pixel-grid check for imagery/masks.
- Uncalibrated signal: call features proxies and seek in-situ observations.
- Validation leakage: group by scene date, hold out contiguous periods.
- Access limitations: manually download authorized products, avoid unapproved bulk acquisition.
