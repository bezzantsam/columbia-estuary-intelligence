"""Read NOAA CO-OPS and USGS continuous observations; UTC, null-aware.

These are in-situ station measurements, not satellite-pixel observations.
Do not interpret simple correlations as independent plume validation.
"""
from __future__ import annotations

import argparse
import csv
from datetime import date, datetime, time, timezone
import json
import os
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlsplit
import requests

NOAA_URL = "https://api.tidesandcurrents.noaa.gov/api/prod/datagetter"
USGS_URL = "https://api.waterdata.usgs.gov/ogcapi/v1/collections/continuous/items"
PORT_WESTWARD = "USGS-14246900"
ASTORIA = "9439040"
USGS_PARAMETERS = {
    "00060": "instantaneous_discharge",
    "72137": "tidally_filtered_discharge",
    "63680": "turbidity",
}


def _dates(start: date, end: date, max_days: int = 28) -> None:
    if end < start:
        raise ValueError("end cannot precede start")
    if (end - start).days > max_days:
        raise ValueError(f"Limit single retrieval to {max_days} days; batch longer periods")


def _number(value: Any) -> float | None:
    if value is None or str(value).strip() in ("", "-", "null", "NaN"):
        return None
    result = float(value)
    if not (-float("inf") < result < float("inf")) or result <= -999900:
        return None
    return result


def _request_json(url: str, params: dict, session: Any = None) -> dict:
    client = session if session is not None else requests
    response = client.get(url, params=params, timeout=45)
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError("Expected JSON object")
    if payload.get("error"):
        raise ValueError(f"Data provider error: {payload['error']}")
    return payload


def fetch_noaa(start: date, end: date, product: str = "water_level",
               station: str = ASTORIA, session: Any = None) -> list[dict]:
    """Read NOAA 6-minute water levels or hourly winds at Astoria, UTC.

    Date range inclusive; values missing from source remain null.
    """
    if product not in ("water_level", "wind"):
        raise ValueError("product must be 'water_level' or 'wind'")
    _dates(start, end)
    params = {
        "begin_date": start.strftime("%Y%m%d"),
        "end_date": end.strftime("%Y%m%d"),
        "station": station,
        "product": product,
        "time_zone": "gmt",
        "units": "metric",
        "application": "ColumbiaEstuaryIntelligence",
        "format": "json",
    }
    if product == "water_level":
        params["datum"] = "MLLW"
    else:
        params["interval"] = "h"
    payload = _request_json(NOAA_URL, params, session)
    if not isinstance(payload.get("data"), list):
        raise ValueError(f"NOAA response has no data array for {station}/{product}")
    rows = []
    for record in payload["data"]:
        stamp = datetime.strptime(record["t"], "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc)
        base = {
            "timestamp_utc": stamp.isoformat(), "source": "NOAA CO-OPS",
            "station": station, "quality": record.get("f"),
        }
        if product == "water_level":
            rows.append({**base, "variable": "water_level_mllw", "value": _number(record.get("v")),
                         "units": "m", "wind_direction_degrees": None, "wind_gust": None})
        else:
            rows.append({**base, "variable": "wind_speed", "value": _number(record.get("s")),
                         "units": "m/s", "wind_direction_degrees": _number(record.get("d")),
                         "wind_gust": _number(record.get("g"))})
    return rows


def fetch_usgs(start: date, end: date, parameter: str = "63680",
               station: str = PORT_WESTWARD, session: Any = None,
               max_pages: int = 10, page_size: int = 1000) -> list[dict]:
    """Retrieve continuous measurements from USGS OGC API using offset pages.

    Timestamp, source unit and provisional/approved status are preserved.
    """
    _dates(start, end)
    if parameter not in USGS_PARAMETERS:
        raise ValueError(f"Unsupported USGS parameter: {parameter}")
    if not 1 <= max_pages <= 50 or not 1 <= page_size <= 10000:
        raise ValueError("Invalid pagination parameters")
    start_iso = datetime.combine(start, time.min, tzinfo=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    end_iso = datetime.combine(end, time.max, tzinfo=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    params = {
        "monitoring_location_id": station, "parameter_code": parameter,
        "time": f"{start_iso}/{end_iso}", "f": "json",
        "limit": page_size, "offset": 0,
    }
    key = os.environ.get("USGS_API_KEY")
    if key:
        params["api_key"] = key
    rows: list[dict] = []
    next_url = USGS_URL
    request_params = params
    visited = set()
    for _ in range(max_pages):
        payload = _request_json(next_url, request_params, session)
        features = payload.get("features")
        if not isinstance(features, list):
            raise ValueError("USGS response lacks GeoJSON features")
        for feature in features:
            props = feature.get("properties", {})
            if props.get("monitoring_location_id") != station or props.get("parameter_code") != parameter:
                raise ValueError("Unexpected USGS station or parameter in response")
            timestamp = datetime.fromisoformat(props["time"].replace("Z", "+00:00"))
            if timestamp.tzinfo is None:
                raise ValueError("USGS timestamp must include timezone")
            rows.append({
                "timestamp_utc": timestamp.astimezone(timezone.utc).isoformat(),
                "source": "USGS", "station": station,
                "variable": USGS_PARAMETERS[parameter], "value": _number(props.get("value")),
                "units": props.get("unit_of_measure"),
                "quality": props.get("approval_status", props.get("approvals_status")),
                "timeseries_id": props.get("time_series_id", props.get("timeseries_id")),
            })
        links = [link.get("href") for link in payload.get("links", [])
                 if link.get("rel") == "next"]
        if not links:
            return rows
        if not features:
            raise ValueError("USGS next page with zero features")
        if not links[0]:
            raise ValueError("USGS next-page link is missing href")
        next_url = urljoin(USGS_URL, links[0])
        parsed = urlsplit(next_url)
        if parsed.scheme != "https" or parsed.hostname != "api.waterdata.usgs.gov" or parsed.port not in (None, 443):
            raise ValueError("Unsafe USGS pagination URL")
        if next_url in visited:
            raise ValueError("USGS pagination loop detected")
        visited.add(next_url)
        request_params = None
    raise ValueError("USGS exceeded max_pages; narrow the time window")


def save_json_csv(rows: list[dict], output: str | Path) -> Path:
    """Serialize observational records with nulls, never interpolating them."""
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.suffix == ".json":
        output.write_text(json.dumps(rows, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    elif output.suffix == ".csv":
        if not rows:
            raise ValueError("Cannot infer CSV columns from no records; use JSON")
        cols = sorted({k for row in rows for k in row})
        with output.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=cols)
            writer.writeheader()
            writer.writerows(rows)
    else:
        raise ValueError("Output must end in .csv or .json")
    return output


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source", choices=("noaa-water", "noaa-wind", "usgs-turbidity",
                                      "usgs-discharge", "usgs-tidal-flow"), required=True)
    p.add_argument("--start", type=date.fromisoformat, required=True)
    p.add_argument("--end", type=date.fromisoformat, required=True)
    p.add_argument("--output", required=True)
    args = p.parse_args(argv)
    lookup = {
        "noaa-water": lambda: fetch_noaa(args.start, args.end),
        "noaa-wind": lambda: fetch_noaa(args.start, args.end, product="wind"),
        "usgs-turbidity": lambda: fetch_usgs(args.start, args.end, parameter="63680"),
        "usgs-discharge": lambda: fetch_usgs(args.start, args.end, parameter="00060"),
        "usgs-tidal-flow": lambda: fetch_usgs(args.start, args.end, parameter="72137"),
    }
    records = lookup[args.source]()
    target = save_json_csv(records, args.output)
    print(f"Saved {len(records)} station observations to {target}; no interpolation.")


if __name__ == "__main__":
    main()
