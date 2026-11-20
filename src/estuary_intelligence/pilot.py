"""Inspect a bounded PlanetScope pilot catalog and asset permissions.

Only catalog search and asset-metadata reads are performed. This command never
activates assets, creates orders, or downloads imagery. A visible scene is not
proof of download permission, and permission is not proof of scientific quality.
"""
from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
import json
import os
from pathlib import Path
import re

import requests

from .search import build_query, load_aoi, search_catalog


ASSET_ROOT = "https://api.planet.com/data/v1/item-types/PSScene/items"
SR_ASSETS = ("ortho_analytic_8b_sr", "ortho_analytic_4b_sr")
MASK_ASSET = "ortho_udm2"
MAX_CANDIDATES = 20
MAX_CATALOG_PAGES = 3
KNOWN_STATUSES = {"active", "inactive", "activating", "failed"}


class PilotRequestError(RuntimeError):
    """A sanitized metadata-request failure; never contains response bodies."""


def build_plan(aoi: dict, start: date, end: date, max_cloud: float = 0.25,
               limit: int = 10) -> dict:
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= MAX_CANDIDATES:
        raise ValueError(f"limit must be an integer between 1 and {MAX_CANDIDATES}")
    return {
        "query": build_query(aoi, start, end, max_cloud),
        "max_candidates": limit,
        "max_catalog_pages": MAX_CATALOG_PAGES,
        "max_asset_metadata_requests": limit,
        "surface_reflectance_preference": list(SR_ASSETS),
        "required_quality_mask": MASK_ASSET,
        "imagery_orders_created": 0,
        "assets_activated": 0,
        "imagery_downloaded": False,
    }


def list_scene_assets(api_key: str, scene_id: str, *, session=None) -> dict:
    """Read asset metadata from a fixed origin without following redirects."""
    if not api_key:
        raise ValueError("PL_API_KEY is required for a live pilot check")
    if not isinstance(scene_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}", scene_id):
        raise ValueError("Invalid PlanetScope scene identifier")
    client = session if session is not None else requests
    try:
        response = client.get(
            f"{ASSET_ROOT}/{scene_id}/assets", auth=(api_key, ""),
            timeout=30, allow_redirects=False,
        )
    except requests.RequestException:
        raise PilotRequestError("asset_request_failed") from None
    if response.status_code != 200:
        # Report only the status code, never a URL, response body, or exception.
        raise PilotRequestError(f"asset_http_{response.status_code}")
    try:
        payload = response.json()
    except ValueError:
        raise PilotRequestError("asset_response_invalid_json") from None
    if not isinstance(payload, dict):
        raise PilotRequestError("asset_response_invalid_structure")
    return payload


def summarize_asset(payload: dict, name: str) -> dict:
    """Allowlist public metadata; deliberately drop location and _links."""
    asset = payload.get(name)
    if not isinstance(asset, dict):
        return {"listed": False, "download_permission": None, "status": "missing"}
    permissions = asset.get("_permissions")
    permission = ("download" in permissions) if isinstance(permissions, list) else None
    status = asset.get("status")
    return {
        "listed": True,
        "download_permission": permission,
        "status": status if isinstance(status, str) and status in KNOWN_STATUSES else "unknown",
    }


def summarize_assets(payload: dict) -> dict:
    assets = {name: summarize_asset(payload, name) for name in (*SR_ASSETS, MASK_ASSET)}
    # Prefer the 8-band asset when both are permitted; permit a 4-band fallback.
    selected = next((name for name in SR_ASSETS if assets[name]["download_permission"] is True), None)
    if selected is None:
        selected = next((name for name in SR_ASSETS if assets[name]["listed"]), None)
    pair = [assets[selected], assets[MASK_ASSET]] if selected else []
    permission_confirmed = bool(pair) and all(x["download_permission"] is True for x in pair)
    both_active = bool(pair) and all(x["status"] == "active" for x in pair)
    if not selected or not assets[MASK_ASSET]["listed"]:
        readiness = "missing_required_assets"
    elif any(x["download_permission"] is False for x in pair):
        readiness = "download_not_authorized"
    elif not permission_confirmed:
        readiness = "download_permission_unconfirmed"
    elif both_active:
        readiness = "permissions_confirmed_assets_active"
    elif any(x["status"] == "failed" for x in pair):
        readiness = "permissions_confirmed_asset_failed"
    elif any(x["status"] == "unknown" for x in pair):
        readiness = "permissions_confirmed_status_unknown"
    else:
        readiness = "permissions_confirmed_activation_needed"
    return {
        "assets": assets,
        "selected_surface_reflectance_asset": selected,
        "quality_mask_asset": MASK_ASSET,
        "pair_download_permission_confirmed": permission_confirmed,
        "both_assets_active": both_active,
        "readiness": readiness,
    }


def run_pilot(*, aoi: dict, start: date, end: date, max_cloud: float = 0.25,
              limit: int = 10, api_key: str = "", dry_run: bool = False,
              session=None) -> dict:
    plan = build_plan(aoi, start, end, max_cloud, limit)
    manifest = {
        "schema_version": "1.0",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "mode": "dry_run" if dry_run else "read_only_metadata",
        "plan": plan,
        "access_expiration": {
            "verified": False,
            "end_date": None,
            "next_step": "Check account plan/product validity or ask the ASU account administrator.",
        },
        "catalog": {"executed": False},
        "scenes": [],
        "scientific_status": "No imagery processed; scene-wide cloud metadata is not AOI water-quality validation.",
    }
    if dry_run:
        return manifest
    if not api_key:
        raise ValueError("PL_API_KEY is required for a live pilot check; use --dry-run without credentials")
    try:
        catalog = search_catalog(
            api_key, plan["query"], limit=limit, page_size=limit,
            max_pages=MAX_CATALOG_PAGES, session=session,
        )
    except requests.RequestException:
        raise PilotRequestError("Planet catalog request failed; check credentials, access and connection.") from None
    manifest["catalog"] = {
        "executed": True,
        "returned_count": catalog["count"],
        "pages_fetched": catalog["pages_fetched"],
        "truncated": catalog["truncated"],
        "selection": "Most recent matching catalog scenes; not a representative seasonal sample.",
    }
    seen = set()
    for scene in catalog["scenes"][:limit]:
        scene_id = scene.get("id")
        if not isinstance(scene_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}", scene_id):
            raise ValueError("Catalog returned an invalid PlanetScope scene identifier")
        if scene_id in seen:
            continue
        seen.add(scene_id)
        # Copy only named metadata fields, never arbitrary item payloads/URLs.
        candidate = {name: scene.get(name) for name in (
            "id", "item_type", "acquired", "cloud_cover", "clear_percent", "instrument",
        )}
        candidate["catalog_visible"] = True
        candidate["inspection_status"] = "complete"
        try:
            candidate.update(summarize_assets(list_scene_assets(api_key, scene_id, session=session)))
        except PilotRequestError as exc:
            candidate.update({"inspection_status": "failed", "readiness": "inspection_failed", "error_code": str(exc)})
        manifest["scenes"].append(candidate)
        if candidate.get("error_code") == "asset_http_401":
            # Authentication failure affects all subsequent requests; stop early.
            break
    manifest["summary"] = {
        "scenes_inspected": len(manifest["scenes"]),
        "pairs_with_download_permission": sum(
            s.get("pair_download_permission_confirmed", False) for s in manifest["scenes"]
        ),
        "inspection_failures": sum(s["inspection_status"] == "failed" for s in manifest["scenes"]),
    }
    return manifest


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", type=date.fromisoformat, required=True)
    parser.add_argument("--end", type=date.fromisoformat, required=True, help="Exclusive end date")
    parser.add_argument("--aoi", default="config/aoi.geojson")
    parser.add_argument("--max-cloud", type=float, default=0.25)
    parser.add_argument("--limit", type=int, default=10, help="Inspect at most 1–20 candidates (default: 10)")
    parser.add_argument("--dry-run", action="store_true", help="Write the request plan without credentials or network calls")
    parser.add_argument("--output", default="outputs/planet_pilot.json")
    args = parser.parse_args(argv)
    try:
        manifest = run_pilot(
            aoi=load_aoi(args.aoi), start=args.start, end=args.end,
            max_cloud=args.max_cloud, limit=args.limit,
            api_key=os.environ.get("PL_API_KEY", ""), dry_run=args.dry_run,
        )
    except PilotRequestError as exc:
        parser.error(str(exc))
    except (ValueError, OSError, RuntimeError):
        # Input/request details can contain tokens. Do not print raw exceptions.
        parser.error("Pilot check failed. Check the AOI, date range, limit, and local PL_API_KEY; no imagery was requested.")
    destination = Path(args.output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(manifest, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    if args.dry_run:
        print(f"Dry-run plan saved to {destination}. No network requests made.")
    else:
        summary = manifest["summary"]
        print(f"Inspected {summary['scenes_inspected']} scene records; "
              f"{summary['pairs_with_download_permission']} SR/mask pairs have download permission. "
              f"Manifest: {destination}. No assets activated, ordered, or downloaded.")
        if summary["inspection_failures"]:
            parser.exit(1, f"{summary['inspection_failures']} asset metadata request(s) failed; "
                        "inspect the sanitized error_code entries in the local manifest.\n")


if __name__ == "__main__":
    main()
