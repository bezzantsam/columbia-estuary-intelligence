from datetime import date
import numpy as np
import rasterio
from rasterio.transform import from_origin
import pytest
from estuary_intelligence.search import build_query, load_aoi
from estuary_intelligence.analyze import extract_features


def test_query_has_date_aoi_and_cloud_limit():
    aoi = load_aoi("config/aoi.geojson")
    p = build_query(aoi, date(2026, 7, 1), date(2026, 8, 1), 0.2)
    assert p["item_types"] == ["PSScene"]
    assert p["geometry"]["type"] == "Polygon"
    assert p["filter"]["config"][1]["config"]["lte"] == 0.2


def _make_tif(path, arr, transform=from_origin(-124.1, 46.3, 0.0001, 0.0001)):
    with rasterio.open(path, "w", driver="GTiff", width=arr.shape[2], height=arr.shape[1],
                       count=arr.shape[0], dtype=arr.dtype, crs="EPSG:4326", transform=transform) as dst:
        dst.write(arr)


def test_four_band_masks_and_scales(tmp_path):
    # Fully synthetic values; no Planet data used in test.
    sr = np.zeros((4, 3, 3), dtype=np.uint16)
    sr[0] = 900     # blue
    sr[1] = 2500    # green
    sr[2] = 1000    # red
    sr[3] = 500     # nir
    udm = np.zeros((8, 3, 3), dtype=np.uint8)
    udm[0] = 1      # clear
    udm[6] = 95     # confidence
    udm[0, 0, 0] = 0  # cloud-flagged pixel not admitted
    _make_tif(tmp_path / "sr.tif", sr)
    _make_tif(tmp_path / "udm.tif", udm)
    r, ndwi, water = extract_features(tmp_path / "sr.tif", tmp_path / "udm.tif")
    assert r["pixel_count"] == 9
    assert r["water_pixel_count"] == 8
    assert r["median_red_reflectance_water"] == pytest.approx(0.1)
    assert r["median_green_reflectance_water"] == pytest.approx(0.25)
    assert r["median_red_green_ratio_water"] == pytest.approx(0.4)
    assert np.isnan(ndwi[0, 0])


def test_eight_band_mapping(tmp_path):
    sr = np.zeros((8, 2, 2), dtype=np.uint16)
    sr[3] = 3000  # green=band4
    sr[5] = 1500  # red=band6
    sr[7] = 1000  # nir=band8
    _make_tif(tmp_path / "sr8.tif", sr)
    r, _, _ = extract_features(tmp_path / "sr8.tif")
    assert r["water_pixel_count"] == 4
    assert r["median_red_reflectance_water"] == pytest.approx(0.15)


def test_misalignment_rejected(tmp_path):
    sr = np.full((4, 2, 2), 1500, dtype=np.uint16)
    udm = np.zeros((8, 2, 2), dtype=np.uint8)
    _make_tif(tmp_path / "sr.tif", sr)
    _make_tif(tmp_path / "udm.tif", udm, transform=from_origin(-124.2, 46.3, 0.0001, 0.0001))
    with pytest.raises(ValueError, match="grids differ"):
        extract_features(tmp_path / "sr.tif", tmp_path / "udm.tif")


def test_saturated_pixel_excluded_even_with_external_mask(tmp_path):
    sr = np.ones((4, 1, 2), dtype=np.uint16) * 1000
    sr[1] = 2500
    sr[2, 0, 1] = 65535
    sr[3] = 500
    udm = np.zeros((8, 1, 2), dtype=np.uint8)
    udm[0] = 1
    udm[6] = 95
    _make_tif(tmp_path / "sr.tif", sr)
    _make_tif(tmp_path / "udm.tif", udm)
    _make_tif(tmp_path / "water.tif", np.ones((1, 1, 2), dtype=np.uint8))
    r, _, _ = extract_features(
        tmp_path / "sr.tif", tmp_path / "udm.tif",
        water_mask_path=tmp_path / "water.tif", water_mask_mode="external")
    assert r["water_pixel_count"] == 1


def test_haze_flag_excluded_even_if_clear_also_set(tmp_path):
    sr = np.ones((4, 1, 2), dtype=np.uint16) * 1000
    sr[1] = 2500
    sr[3] = 500
    udm = np.zeros((8, 1, 2), dtype=np.uint8)
    udm[0] = 1
    udm[6] = 95
    udm[3, 0, 1] = 1
    _make_tif(tmp_path / "sr.tif", sr)
    _make_tif(tmp_path / "udm.tif", udm)
    r, _, _ = extract_features(tmp_path / "sr.tif", tmp_path / "udm.tif")
    assert r["water_pixel_count"] == 1
