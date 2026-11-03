"""Extract preliminary optical features from PlanetScope surface-reflectance scenes.

No value reported here is a validated measurement of sediment concentration.
"""
from __future__ import annotations
import argparse
import csv
from pathlib import Path
import numpy as np
import rasterio
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from .watermask import load_water_mask

BANDS = {
    4: {"blue": 1, "green": 2, "red": 3, "nir": 4},
    8: {"blue": 2, "green": 4, "red": 6, "nir": 8},
}


def extract_features(sr_path: str | Path, udm_path: str | Path | None = None,
                     min_confidence: int = 70, ndwi_threshold: float = 0.0,
                     water_mask_path: str | Path | None = None,
                     water_mask_mode: str = "ndwi") -> tuple[dict, np.ndarray, np.ndarray]:
    if not 0 <= min_confidence <= 100:
        raise ValueError("min_confidence must be between 0 and 100")
    if water_mask_mode not in ("ndwi", "external", "external_and_ndwi"):
        raise ValueError("water_mask_mode must be ndwi, external or external_and_ndwi")
    if water_mask_mode != "ndwi" and water_mask_path is None:
        raise ValueError("External water-mask mode requires water_mask_path")
    with rasterio.open(sr_path) as sr:
        if sr.count not in BANDS:
            raise ValueError(f"Expected 4-band or 8-band PlanetScope SR image; got {sr.count} bands")
        bands = BANDS[sr.count]
        green = sr.read(bands["green"]).astype("float32") / 10000.0
        red = sr.read(bands["red"]).astype("float32") / 10000.0
        nir = sr.read(bands["nir"]).astype("float32") / 10000.0
        valid = (sr.read_masks(bands["green"]) > 0)
        valid &= sr.read_masks(bands["red"]) > 0
        valid &= sr.read_masks(bands["nir"]) > 0
        valid &= np.isfinite(green) & np.isfinite(red) & np.isfinite(nir)
        valid &= (green > 0) & (red > 0) & (nir >= 0)
        # Out-of-range/saturated DN values are not usable water reflectance.
        valid &= (green <= 1.5) & (red <= 1.5) & (nir <= 1.5)
        sr_shape, sr_crs, sr_transform = sr.shape, sr.crs, sr.transform
        band_count = sr.count

    if udm_path is not None:
        with rasterio.open(udm_path) as mask:
            if mask.count < 8:
                raise ValueError("Expected UDM2 file with 8 bands")
            if mask.shape != sr_shape or mask.crs != sr_crs or not mask.transform.almost_equals(sr_transform):
                raise ValueError("UDM2 and surface-reflectance grids differ. Align/crop both with GIS tools first.")
            clear = mask.read(1) == 1
            class_flags_ok = (mask.read(2) == 0) & (mask.read(3) == 0)
            class_flags_ok &= (mask.read(4) == 0) & (mask.read(5) == 0)
            class_flags_ok &= mask.read(6) == 0
            confidence = mask.read(7) >= min_confidence
            pixel_flags_ok = mask.read(8) == 0
            valid &= clear & class_flags_ok & confidence & pixel_flags_ok

    denominator = green + nir
    ndwi = np.full(green.shape, np.nan, dtype="float32")
    idx = valid & (denominator > 1e-6)
    ndwi[idx] = (green[idx] - nir[idx]) / denominator[idx]
    ndwi_water = idx & (ndwi > ndwi_threshold)
    if water_mask_mode == "ndwi":
        water = ndwi_water
        excluded_by_ndwi = 0
    else:
        independent_water = load_water_mask(
            water_mask_path, shape=sr_shape, crs=sr_crs,
            transform=sr_transform,
        )
        externally_designated = idx & independent_water
        excluded_by_ndwi = int((externally_designated & ~ndwi_water).sum())
        if water_mask_mode == "external":
            water = externally_designated
        else:
            water = externally_designated & ndwi_water
            excluded_by_ndwi = 0
    red_green_ratio = np.full(green.shape, np.nan, dtype="float32")
    red_green_ratio[water] = red[water] / np.maximum(green[water], 1e-6)

    def safe_median(a: np.ndarray, mask: np.ndarray) -> float | None:
        return float(np.median(a[mask])) if mask.any() else None

    result = {
        "pixel_count": int(green.size),
        "band_count": int(band_count),
        "clear_valid_fraction": float(valid.sum() / valid.size),
        "water_pixel_count": int(water.sum()),
        "water_mask_mode": water_mask_mode,
        "water_pixels_that_ndwi_would_exclude": excluded_by_ndwi,
        "water_fraction_of_clear": (float(water.sum() / valid.sum()) if valid.any() else None),
        "median_ndwi_water": safe_median(ndwi, water),
        "median_red_reflectance_water": safe_median(red, water),
        "median_green_reflectance_water": safe_median(green, water),
        "median_red_green_ratio_water": safe_median(red_green_ratio, water),
        "interpretation": "uncalibrated optical features; not turbidity NTU or validated plume extent",
    }
    return result, ndwi, water


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--surface-reflectance", required=True)
    p.add_argument("--udm2", help="Strongly recommended UDM2 quality mask")
    p.add_argument("--scene-id", required=True)
    p.add_argument("--acquired", required=True, help="YYYY-MM-DD; source should be Planet metadata")
    p.add_argument("--min-confidence", type=int, default=70)
    p.add_argument("--ndwi-threshold", type=float, default=0.0)
    p.add_argument("--water-mask", help="Optional independent binary 0/1 water mask GeoTIFF")
    p.add_argument("--water-mask-mode", choices=("ndwi", "external", "external_and_ndwi"), default="ndwi")
    p.add_argument("--output-csv", default="outputs/scene_features.csv")
    p.add_argument("--output-png", default="outputs/scene_preview.png")
    p.add_argument("--output-provenance", default="outputs/scene_provenance.json")
    args = p.parse_args(argv)
    if not args.udm2:
        p.error("UDM2 is required for this version's operational workflow; no unmasked results")
    from datetime import date
    date.fromisoformat(args.acquired)
    result, ndwi, water = extract_features(args.surface_reflectance, args.udm2,
                                           args.min_confidence, args.ndwi_threshold,
                                           water_mask_path=args.water_mask,
                                           water_mask_mode=args.water_mask_mode)
    result = {"scene_id": args.scene_id, "acquired": args.acquired, **result}
    dest = Path(args.output_csv)
    dest.parent.mkdir(parents=True, exist_ok=True)
    existing = dest.exists()
    with dest.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(result))
        if not existing:
            writer.writeheader()
        writer.writerow(result)
    fig, ax = plt.subplots(figsize=(9, 6))
    display = np.ma.masked_invalid(ndwi)
    mappable = ax.imshow(display, cmap="BrBG", vmin=-0.5, vmax=0.5)
    ax.contour(water.astype("int"), levels=[0.5], colors="black", linewidths=0.3)
    ax.set_title(f"Exploratory NDWI | {args.scene_id} | {args.acquired}")
    ax.set_xlabel("Image column (not latitude/longitude)")
    ax.set_ylabel("Image row (not latitude/longitude)")
    fig.colorbar(mappable, ax=ax, label="NDWI (unitless)")
    fig.text(0.5, 0.01, "Unvalidated optical proxy • noncommercial research • check Planet publication permission", ha="center", fontsize=8)
    fig.tight_layout(rect=[0, 0.04, 1, 1])
    from estuary_intelligence.provenance import build_provenance, save_provenance
    provenance = build_provenance(
        scene_id=args.scene_id, acquired=args.acquired,
        surface_reflectance=args.surface_reflectance, udm2=args.udm2,
        min_confidence=args.min_confidence, ndwi_threshold=args.ndwi_threshold,
        features=result,
    )
    provenance["processing"]["water_mask_mode"] = args.water_mask_mode
    provenance["processing"]["external_water_mask_filename"] = (
        Path(args.water_mask).name if args.water_mask else None
    )
    saved_provenance = save_provenance(provenance, args.output_provenance)
    imgdest = Path(args.output_png)
    imgdest.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(imgdest, dpi=130)
    plt.close(fig)
    print(f"Saved {dest}, {imgdest} and {saved_provenance}. Water pixels: {result['water_pixel_count']}. NOT a calibrated sediment estimate.")


if __name__ == "__main__":
    main()
