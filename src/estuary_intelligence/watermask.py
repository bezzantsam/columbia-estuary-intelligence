"""Load an independent binary water mask aligned to a surface-reflectance raster.

A value of 1 means manually or independently designated water, 0 means excluded.
This input is *not* proof of water extent; its methodology must be documented.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import rasterio


def load_water_mask(
    path: str | Path, *, shape: tuple[int, int], crs, transform
) -> np.ndarray:
    """Return a boolean mask, rejecting invalid labels or mismatched grids.

    Input must be a single-band GeoTIFF with values 0/1. Masked/no-data pixels
    are excluded, never interpreted as water. Reproject externally first.
    """
    with rasterio.open(path) as src:
        if src.count != 1:
            raise ValueError("Independent water mask must contain exactly one band")
        if (src.shape != shape or src.crs != crs or
                not src.transform.almost_equals(transform)):
            raise ValueError("Water-mask and surface-reflectance grids differ; align before processing")
        pixels = src.read(1)
        available = src.read_masks(1) > 0
        if not np.all(np.isin(pixels[available], (0, 1))):
            raise ValueError("Independent water mask accepts only 0 and 1 labels")
        return available & (pixels == 1)
