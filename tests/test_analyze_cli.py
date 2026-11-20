"""Operational scene outputs retain acquisition time and each scene's evidence."""
import csv
import json

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

from estuary_intelligence.analyze import main


@pytest.fixture
def raster_inputs(tmp_path):
    sr = np.full((4, 2, 2), 1000, dtype="uint16")
    sr[1] = 2500
    sr[3] = 500
    sr[3, 1, 1] = 3500  # One land-like pixel gives the preview a water boundary.
    udm = np.zeros((8, 2, 2), dtype="uint8")
    udm[0] = 1
    udm[6] = 95
    paths = []
    for name, pixels in (("sr.tif", sr), ("udm.tif", udm)):
        path = tmp_path / name
        with rasterio.open(path, "w", driver="GTiff", width=2, height=2,
                           count=pixels.shape[0], dtype=pixels.dtype, crs="EPSG:4326",
                           transform=from_origin(-124.0, 46.3, 0.0001, 0.0001)) as ds:
            ds.write(pixels)
        paths.append(path)
    return paths


def _args(inputs, scene="SCENE_1", acquired="2026-07-18T18:42:13.123456Z"):
    return ["--surface-reflectance", str(inputs[0]), "--udm2", str(inputs[1]),
            "--scene-id", scene, "--acquired", acquired]


def test_distinct_scene_outputs_preserve_full_utc_timestamp(tmp_path, monkeypatch, raster_inputs):
    monkeypatch.chdir(tmp_path)
    for scene, stamp in (("SCENE_1", "2026-07-18T18:42:13.123456Z"),
                         ("SCENE_2", "2026-07-18T11:42:13.123456-07:00")):
        main(_args(raster_inputs, scene, stamp))
    for scene in ("SCENE_1", "SCENE_2"):
        output = tmp_path / "outputs" / scene
        with (output / "scene_features.csv").open(newline="") as f:
            rows = list(csv.DictReader(f))
        assert len(rows) == 1
        assert rows[0]["scene_id"] == scene
        assert rows[0]["acquired"] == "2026-07-18T18:42:13.123456+00:00"
        assert rows[0]["acquired_date"] == "2026-07-18"
        provenance = json.loads((output / "scene_provenance.json").read_text())
        assert provenance["scene_id"] == scene
        assert provenance["acquired_utc"] == rows[0]["acquired"]
        assert (output / "scene_preview.png").read_bytes().startswith(b"\x89PNG")


@pytest.mark.parametrize("stamp", ["2026-07-18", "2026-07-18T18:42:13", "not-a-date"])
def test_invalid_timestamp_fails_before_any_outputs(tmp_path, monkeypatch, capsys, stamp):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit) as exc:
        main(_args(["not-read-sr.tif", "not-read-udm.tif"], acquired=stamp))
    assert exc.value.code == 2
    assert "timezone" in capsys.readouterr().err
    assert not (tmp_path / "outputs").exists()


def test_existing_scene_outputs_are_not_replaced_or_appended(tmp_path, monkeypatch, capsys, raster_inputs):
    monkeypatch.chdir(tmp_path)
    main(_args(raster_inputs))
    originals = {p: p.read_bytes() for p in (tmp_path / "outputs" / "SCENE_1").iterdir()}
    with pytest.raises(SystemExit) as exc:
        main(_args(raster_inputs))
    assert exc.value.code == 2
    assert "Output already exists" in capsys.readouterr().err
    assert {p: p.read_bytes() for p in originals} == originals


def test_scene_id_cannot_escape_output_directory(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit) as exc:
        main(_args(["not-read-sr.tif", "not-read-udm.tif"], scene="../../escape"))
    assert exc.value.code == 2
    assert "Scene ID" in capsys.readouterr().err
    assert not (tmp_path / "outputs").exists()


def test_output_destinations_must_be_distinct(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit) as exc:
        main(_args(["not-read-sr.tif", "not-read-udm.tif"]) +
             ["--output-csv", "same-file", "--output-provenance", "same-file"])
    assert exc.value.code == 2
    assert "must be different files" in capsys.readouterr().err
    assert not (tmp_path / "outputs").exists()
    assert not (tmp_path / "same-file").exists()
