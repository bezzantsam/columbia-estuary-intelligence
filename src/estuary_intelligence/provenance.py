"""Reproducible local metadata for PlanetScope optical-feature outputs.

Records no image pixels, signed asset URLs, or credentials. Never publish
licensed imagery without authorization under the applicable Planet agreement.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import subprocess

import numpy
import rasterio


def file_sha256(path: str | Path) -> str:
    """Compute content hash in fixed-size chunks without loading raster into RAM."""
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        while chunk := f.read(1024 * 1024):
            h.update(chunk)
    return h.hexdigest()


def current_git_commit() -> str | None:
    """Best-effort Git revision identifier; supports installed distributions."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=True, capture_output=True, text=True, timeout=5,
        )
        return result.stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def build_provenance(
    *, scene_id: str, acquired: str,
    surface_reflectance: str | Path, udm2: str | Path,
    min_confidence: int, ndwi_threshold: float,
    features: dict,
) -> dict:
    """Make an audit record for a processed scene, excluding raw imagery.

    Scene id and acquisition date must come from official Planet item metadata,
    not inferred from the image filename.
    """
    sr_path, udm_path = Path(surface_reflectance), Path(udm2)
    with rasterio.open(sr_path) as ds:
        image_metadata = {
            "crs": str(ds.crs) if ds.crs else None,
            "width": ds.width,
            "height": ds.height,
            "bands": ds.count,
            "band_descriptions": list(ds.descriptions),
            "affine_transform": list(ds.transform)[:6],
        }
    return {
        "schema_version": "1.0",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "scene_id": scene_id,
        "acquired_date": acquired,
        "asset_type_assumption": "PlanetScope 4- or 8-band surface reflectance + aligned UDM2",
        "inputs": {
            "surface_reflectance": {"filename": sr_path.name, "sha256": file_sha256(sr_path)},
            "udm2": {"filename": udm_path.name, "sha256": file_sha256(udm_path)},
        },
        "image_metadata": image_metadata,
        "processing": {
            "reflectance_scale_divisor": 10000,
            "udm_clear_band": 1,
            "udm_confidence_band": 7,
            "udm_unusable_flags_band": 8,
            "unusable_flags_policy": "require zero",
            "min_clear_confidence": min_confidence,
            "ndwi_threshold": ndwi_threshold,
        },
        "software": {
            "git_commit": current_git_commit(),
            "python": platform.python_version(),
            "numpy": numpy.__version__,
            "rasterio": rasterio.__version__,
        },
        "features": features,
        "scientific_caveat": "Exploratory optical proxies only. No calibrated turbidity or plume extent.",
    }


def save_provenance(record: dict, destination: str | Path) -> Path:
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(record, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    return destination
