"""Read-only Planet Data API catalog search. Never orders or downloads data."""
from __future__ import annotations
import argparse
from datetime import date
import json
import os
from pathlib import Path
from urllib.parse import urljoin, urlsplit
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


def search_catalog(api_key: str, query: dict, limit: int = 50,
                   page_size: int = 50, max_pages: int = 100,
                   session=None) -> dict:
    """Return at most limit scene records, following Planet pagination.

    limit is a total-output cap, not a per-page limit. Explicitly reports
    truncation; rejects unsafe pagination URLs before forwarding credentials.
    """
    if not api_key:
        raise ValueError("PL_API_KEY not set; wait for Planet account activation")
    if not 1 <= limit <= 10000:
        raise ValueError("limit must be between 1 and 10000")
    if not 1 <= page_size <= 250 or not 1 <= max_pages <= 100:
        raise ValueError("page_size must be 1..250 and max_pages must be 1..100")
    client = session if session is not None else requests
    auth = (api_key, "")
    response = client.post(
        API_URL,
        params={"_page_size": min(page_size, limit), "_sort": "acquired desc"},
        auth=auth,
        headers={"Content-Type": "application/json"},
        json=query,
        timeout=60,
    )
    response.raise_for_status()
    features = []
    pages_fetched = 0
    seen_links = set()
    truncated = False
    while True:
        payload = response.json()
        pages_fetched += 1
        if not isinstance(payload, dict) or not isinstance(payload.get("features"), list):
            raise ValueError("Unexpected Planet catalog response structure")
        for item in payload["features"]:
            properties = item.get("properties", {})
            features.append({
                "id": item.get("id"),
                "acquired": properties.get("acquired"),
                "cloud_cover": properties.get("cloud_cover"),
                "clear_percent": properties.get("clear_percent"),
                "instrument": properties.get("instrument"),
                "item_type": item.get("type"),
            })
            if len(features) == limit:
                break
        raw_next = (payload.get("_links") or {}).get("_next")
        if len(features) == limit:
            truncated = bool(raw_next) or len(payload["features"]) > limit
            break
        if not raw_next:
            break
        if pages_fetched >= max_pages:
            raise RuntimeError("Planet pagination exceeded max_pages; narrow the search")
        next_url = urljoin(API_URL, raw_next)
        u = urlsplit(next_url)
        if u.scheme != "https" or u.hostname != "api.planet.com" or u.port not in (None, 443):
            raise ValueError("Unsafe Planet pagination URL; credentials not forwarded")
        if next_url in seen_links:
            raise ValueError("Planet pagination loop detected")
        seen_links.add(next_url)
        response = client.get(next_url, auth=auth, timeout=60)
        response.raise_for_status()
    return {"catalog_only": True, "count": len(features), "pages_fetched": pages_fetched,
            "truncated": truncated, "scenes": features}


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", type=date.fromisoformat, required=True)
    parser.add_argument("--end", type=date.fromisoformat, required=True, help="Exclusive end date")
    parser.add_argument("--max-cloud", type=float, default=0.25)
    parser.add_argument("--aoi", default="config/aoi.geojson")
    parser.add_argument("--output", default="outputs/planet_catalog.json")
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--page-size", type=int, default=50)
    args = parser.parse_args(argv)
    api_key = os.environ.get("PL_API_KEY", "")
    if not api_key:
        parser.error("Planet account API key required in local PL_API_KEY environment variable")
    out = search_catalog(api_key, build_query(load_aoi(args.aoi), args.start, args.end, args.max_cloud), args.limit, page_size=args.page_size)
    dest = Path(args.output)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(out, indent=2) + "\n")
    print(f"Catalog search complete: saved {out['count']} scene metadata records to {dest}. No imagery ordered or downloaded.")


if __name__ == "__main__":
    main()
