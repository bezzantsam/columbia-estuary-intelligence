import hashlib
import json

import numpy as np
import rasterio
from rasterio.transform import from_origin
import pytest

from estuary_intelligence.provenance import (
    acquisition_timestamp_utc, build_provenance, file_sha256, save_provenance,
)


def test_file_hash(tmp_path):
    p = tmp_path / "example.bin"
    p.write_bytes(b"abc")
    assert file_sha256(p) == hashlib.sha256(b"abc").hexdigest()


def test_provenance_roundtrip_no_pixels_or_credentials(tmp_path):
    sr = tmp_path / "mock_sr.tif"
    udm = tmp_path / "mock_udm.tif"
    for path, n in ((sr, 4), (udm, 8)):
        with rasterio.open(path, "w", driver="GTiff", width=2, height=2,
            count=n, dtype="uint16", crs="EPSG:4326",
            transform=from_origin(-124.0, 46.3, 0.0001, 0.0001)) as ds:
            ds.write(np.zeros((n, 2, 2), dtype="uint16"))
    data = build_provenance(scene_id="TEST-SCENE", acquired="2026-07-01T18:42:13.123456Z",
        surface_reflectance=sr, udm2=udm, min_confidence=70,
        ndwi_threshold=0, features={"water_pixel_count": 0})
    path = save_provenance(data, tmp_path / "output" / "provenance.json")
    recovered = json.loads(path.read_text())
    assert recovered["scene_id"] == "TEST-SCENE"
    assert recovered["acquired_utc"] == "2026-07-01T18:42:13.123456+00:00"
    assert recovered["acquired_date"] == "2026-07-01"
    assert recovered["image_metadata"]["bands"] == 4
    assert recovered["inputs"]["surface_reflectance"]["sha256"] == file_sha256(sr)
    assert recovered["processing"]["min_clear_confidence"] == 70
    assert "pixel_values" not in recovered


def test_acquisition_offset_changes_utc_date_without_losing_precision():
    assert acquisition_timestamp_utc("2026-07-18T23:42:13.123456-07:00") == (
        "2026-07-19T06:42:13.123456+00:00"
    )


@pytest.mark.parametrize("value", ["2026-07-18", "2026-07-18T18:42:13", "invalid"])
def test_acquisition_requires_an_instant_with_timezone(value):
    with pytest.raises(ValueError, match="full ISO 8601 timestamp with a timezone"):
        acquisition_timestamp_utc(value)


def test_external_water_mask_is_hashed_even_when_filename_is_unchanged(tmp_path):
    sr, udm, water = (tmp_path / name for name in ("sr.tif", "udm.tif", "water.tif"))

    def write(path, count, pixels):
        with rasterio.open(path, "w", driver="GTiff", width=2, height=2,
                           count=count, dtype="uint16", crs="EPSG:4326",
                           transform=from_origin(-124.0, 46.3, 0.0001, 0.0001)) as ds:
            ds.write(pixels)

    write(sr, 4, np.zeros((4, 2, 2), dtype="uint16"))
    write(udm, 8, np.zeros((8, 2, 2), dtype="uint16"))
    write(water, 1, np.ones((1, 2, 2), dtype="uint16"))
    kwargs = dict(scene_id="TEST-SCENE", acquired="2026-07-01T18:42:13Z",
                  surface_reflectance=sr, udm2=udm, min_confidence=70,
                  ndwi_threshold=0, features={}, water_mask_path=water,
                  water_mask_mode="external")
    first = build_provenance(**kwargs)
    assert first["inputs"]["external_water_mask"]["sha256"] == file_sha256(water)
    write(water, 1, np.zeros((1, 2, 2), dtype="uint16"))
    second = build_provenance(**kwargs)
    assert first["inputs"]["external_water_mask"]["filename"] == second["inputs"]["external_water_mask"]["filename"]
    assert first["inputs"]["external_water_mask"]["sha256"] != second["inputs"]["external_water_mask"]["sha256"]
    assert second["processing"]["water_mask_mode"] == "external"
