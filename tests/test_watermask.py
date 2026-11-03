"""Tests for external land/water designations and NDWI exclusion bias."""

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

from estuary_intelligence.analyze import extract_features
from estuary_intelligence.watermask import load_water_mask


def _write(path, arr, transform=None, nodata=None):
    if transform is None:
        transform = from_origin(-124.1, 46.3, 0.0001, 0.0001)
    with rasterio.open(path, "w", driver="GTiff", width=arr.shape[2],
                       height=arr.shape[1], count=arr.shape[0], dtype=arr.dtype,
                       crs="EPSG:4326", transform=transform, nodata=nodata) as dst:
        dst.write(arr)


def test_external_mask_keeps_low_ndwi_turbid_water(tmp_path):
    # Two synthetic water pixels; one has NIR>green and NDWI<0.
    sr = np.full((4, 1, 2), 1000, dtype=np.uint16)
    sr[1, 0] = [2200, 900]   # green
    sr[2, 0] = [1100, 2500]  # red
    sr[3, 0] = [700, 2000]   # NIR; second pixel NDWI < 0
    udm = np.zeros((8, 1, 2), dtype=np.uint8)
    udm[0] = 1
    udm[6] = 95
    water = np.ones((1, 1, 2), dtype=np.uint8)
    _write(tmp_path / "sr.tif", sr)
    _write(tmp_path / "udm.tif", udm)
    _write(tmp_path / "water.tif", water)

    legacy, _, _ = extract_features(tmp_path / "sr.tif", tmp_path / "udm.tif")
    assert legacy["water_pixel_count"] == 1
    new, _, new_water = extract_features(
        tmp_path / "sr.tif", tmp_path / "udm.tif",
        water_mask_path=tmp_path / "water.tif", water_mask_mode="external")
    assert new["water_pixel_count"] == 2
    assert new["water_pixels_that_ndwi_would_exclude"] == 1
    assert bool(new_water[0, 1])
    assert new["median_red_reflectance_water"] == pytest.approx(0.18)


def test_external_mask_rejects_grid_mismatch(tmp_path):
    sr = np.full((4, 1, 2), 1000, dtype=np.uint16)
    _write(tmp_path / "sr.tif", sr)
    _write(tmp_path / "bad.tif", np.ones((1, 1, 2), dtype=np.uint8),
           transform=from_origin(-123.4, 46.3, 0.0001, 0.0001))
    with rasterio.open(tmp_path / "sr.tif") as ds:
        with pytest.raises(ValueError, match="grids differ"):
            load_water_mask(tmp_path / "bad.tif", shape=ds.shape,
                            crs=ds.crs, transform=ds.transform)


def test_external_mask_rejects_nonbinary_labels(tmp_path):
    _write(tmp_path / "invalid.tif", np.array([[[0, 1, 2]]], dtype=np.uint8))
    with rasterio.open(tmp_path / "invalid.tif") as ds:
        with pytest.raises(ValueError, match="only 0 and 1"):
            load_water_mask(tmp_path / "invalid.tif", shape=ds.shape,
                            crs=ds.crs, transform=ds.transform)


def test_external_mask_mode_requires_file(tmp_path):
    _write(tmp_path / "sr.tif", np.ones((4, 1, 1), dtype=np.uint16))
    with pytest.raises(ValueError, match="requires water_mask_path"):
        extract_features(tmp_path / "sr.tif", water_mask_mode="external")


def test_external_and_ndwi_is_sensitivity_only(tmp_path):
    sr = np.full((4, 1, 2), 1000, dtype=np.uint16)
    sr[1, 0] = [2200, 900]
    sr[3, 0] = [700, 2000]
    _write(tmp_path / "sr.tif", sr)
    _write(tmp_path / "water.tif", np.ones((1, 1, 2), dtype=np.uint8))
    r, _, _ = extract_features(tmp_path / "sr.tif",
        water_mask_path=tmp_path / "water.tif",
        water_mask_mode="external_and_ndwi")
    assert r["water_pixel_count"] == 1
    assert r["water_pixels_that_ndwi_would_exclude"] == 0
