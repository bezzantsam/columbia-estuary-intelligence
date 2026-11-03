"""Read-only Planet Data API catalog search. Never orders or downloads data."""
from __future__ import annotations
import argparse
from datetime import date
import json
import os
from pathlib import Path
import requests

API_URL = "https://api.planet.com/data/v1/quick-search"


def load_aoi(path: str | Path) -> dict:
    data = json.loads(Path(path).read_text())
    if data.get("type") == "FeatureCollection":
        features = data.get("features", [])
        if len(features) != 1:
            raise ValueError("Expected exactly one AOI feature")
        return features[0]["geometry"]
    if data.get("type") == "Feature":
        return data["geometry"]
    if data.get("type") in ("Polygon", "MultiPolygon"):
        return data
    raise ValueError("AOI must be a GeoJSON Polygon/Feature/FeatureCollection")


def build_query(aoi: dict, start: date, end: date, max_cloud: float = 0.25) -> dict:
    if end <= start:
        raise ValueError("End date must be after start date; end is exclusive")
    if not 0 <= max_cloud <= 1:
        raise ValueError("Cloud cover must be a fraction from 0 to 1")
    return {
        "item_types": ["PSScene"],
        "geometry": aoi,
        "filter": {
            "type": "AndFilter",
            "config": [
                {"type": "DateRangeFilter", "field_name": "acquired", "config": {
                    "gte": f"{start.isoformat()}T00:00:00Z",
                    "lt": f"{end.isoformat()}T00:00:00Z"}},
                {"type": "RangeFilter", "field_name": "cloud_cover", "config": {"lte": max_cloud}},
            ],
        },
    }


def search_catalog(api_key: str, query: dict, limit: int = 50) -> dict:
    if not api_key:
        raise ValueError("PL_API_KEY not set; wait for Planet account activation")
    if not 1 <= limit <= 250:
        raise ValueError("limit must be between 1 and 250")
    response = requests.post(
        API_URL,
        params={"_page_size": limit, "_sort": "acquired desc"},
        auth=(api_key, ""),
        headers={"Content-Type": "application/json"},
        json=query,
        timeout=60,
    )
    response.raise_for_status()
    payload = response.json()
    features = []
    for item in payload.get("features", []):
        properties = item.get("properties", {})
        features.append({
            "id": item.get("id"),
            "acquired": properties.get("acquired"),
            "cloud_cover": properties.get("cloud_cover"),
            "clear_percent": properties.get("clear_percent"),
            "instrument": properties.get("instrument"),
            "item_type": item.get("type"),
        })
    return {"catalog_only": True, "count": len(features), "scenes": features}


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", type=date.fromisoformat, required=True)
    parser.add_argument("--end", type=date.fromisoformat, required=True, help="Exclusive end date")
    parser.add_argument("--max-cloud", type=float, default=0.25)
    parser.add_argument("--aoi", default="config/aoi.geojson")
    parser.add_argument("--output", default="outputs/planet_catalog.json")
    parser.add_argument("--limit", type=int, default=50)
    args = parser.parse_args(argv)
    api_key = os.environ.get("PL_API_KEY", "")
    if not api_key:
        parser.error("Planet account API key required in local PL_API_KEY environment variable")
    out = search_catalog(api_key, build_query(load_aoi(args.aoi), args.start, args.end, args.max_cloud), args.limit)
    dest = Path(args.output)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(out, indent=2) + "\n")
    print(f"Catalog search complete: saved {out['count']} scene metadata records to {dest}. No imagery ordered or downloaded.")


if __name__ == "__main__":
    main()
