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


def acquisition_timestamp_utc(value: str) -> str:
    """Validate an acquisition instant and retain it as timezone-aware UTC.

    A date alone is not enough to associate a satellite observation with tides.
    Never invent midnight or assume a timezone for incomplete metadata.
    """
    message = (
        "Acquisition time must be a full ISO 8601 timestamp with a timezone "
        "(for example 2026-07-18T18:42:13.123456Z); copy the acquired value "
        "from Planet scene metadata. Date-only and timezone-free values are not accepted."
    )
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, TypeError, ValueError) as exc:
        raise ValueError(message) from exc
    if stamp.tzinfo is None or stamp.utcoffset() is None:
        raise ValueError(message)
    return stamp.astimezone(timezone.utc).isoformat()


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
    water_mask_path: str | Path | None = None,
    water_mask_mode: str = "ndwi",
) -> dict:
    """Make an audit record for a processed scene, excluding raw imagery.

    Scene id and acquisition timestamp must come from official Planet item metadata,
    not inferred from the image filename.
    """
    acquired_utc = acquisition_timestamp_utc(acquired)
    if water_mask_mode not in ("ndwi", "external", "external_and_ndwi"):
        raise ValueError("Unknown water-mask mode")
    if water_mask_mode != "ndwi" and water_mask_path is None:
        raise ValueError("External water-mask provenance requires water_mask_path")
    sr_path, udm_path = Path(surface_reflectance), Path(udm2)
    inputs = {
        "surface_reflectance": {"filename": sr_path.name, "sha256": file_sha256(sr_path)},
        "udm2": {"filename": udm_path.name, "sha256": file_sha256(udm_path)},
    }
    external_mask = Path(water_mask_path) if water_mask_mode != "ndwi" else None
    if external_mask is not None:
        inputs["external_water_mask"] = {
            "filename": external_mask.name, "sha256": file_sha256(external_mask),
        }
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
        "schema_version": "1.1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "scene_id": scene_id,
        "acquired_utc": acquired_utc,
        "acquired_date": acquired_utc[:10],
        "asset_type_assumption": "PlanetScope 4- or 8-band surface reflectance + aligned UDM2",
        "inputs": inputs,
        "image_metadata": image_metadata,
        "processing": {
            "reflectance_scale_divisor": 10000,
            "udm_clear_band": 1,
            "udm_confidence_band": 7,
            "udm_unusable_flags_band": 8,
            "unusable_flags_policy": "require zero",
            "min_clear_confidence": min_confidence,
            "ndwi_threshold": ndwi_threshold,
            "water_mask_mode": water_mask_mode,
            "external_water_mask_filename": external_mask.name if external_mask else None,
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


def save_provenance(record: dict, destination: str | Path, *, overwrite: bool = True) -> Path:
    destination = Path(destination)
    serialized = json.dumps(record, indent=2, allow_nan=False) + "\n"
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w" if overwrite else "x", encoding="utf-8") as f:
        f.write(serialized)
    return destination
