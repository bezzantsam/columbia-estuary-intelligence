import hashlib
import json

import numpy as np
import rasterio
from rasterio.transform import from_origin

from estuary_intelligence.provenance import build_provenance, file_sha256, save_provenance


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
    data = build_provenance(scene_id="TEST-SCENE", acquired="2026-07-01",
        surface_reflectance=sr, udm2=udm, min_confidence=70,
        ndwi_threshold=0, features={"water_pixel_count": 0})
    path = save_provenance(data, tmp_path / "output" / "provenance.json")
    recovered = json.loads(path.read_text())
    assert recovered["scene_id"] == "TEST-SCENE"
    assert recovered["image_metadata"]["bands"] == 4
    assert recovered["inputs"]["surface_reflectance"]["sha256"] == file_sha256(sr)
    assert recovered["processing"]["min_clear_confidence"] == 70
    assert "pixel_values" not in recovered
