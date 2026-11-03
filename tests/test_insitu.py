"""Synthetic, offline fixtures for NOAA/USGS API ingestion."""
from datetime import date
import json
import pytest
from estuary_intelligence.insitu import fetch_noaa, fetch_usgs, save_json_csv


class Response:
    def __init__(self, data):
        self.data = data

    def raise_for_status(self):
        pass

    def json(self):
        return self.data


class Session:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.requests = []

    def get(self, url, *, params, timeout):
        self.requests.append((url, dict(params)))
        return Response(self.responses.pop(0))


def test_noaa_water_levels_use_utc_and_datum():
    s = Session({"data": [
        {"t": "2026-07-01 01:00", "v": "1.4", "f": "0,0,0,0"},
        {"t": "2026-07-01 01:06", "v": "", "f": "1,0,0,0"},
    ]})
    rows = fetch_noaa(date(2026, 7, 1), date(2026, 7, 1), session=s)
    assert rows[0]["timestamp_utc"] == "2026-07-01T01:00:00+00:00"
    assert rows[0]["value"] == 1.4
    assert rows[1]["value"] is None
    assert s.requests[0][1]["time_zone"] == "gmt"
    assert s.requests[0][1]["datum"] == "MLLW"


def test_noaa_wind_includes_direction_and_gust():
    s = Session({"data": [{"t": "2026-07-01 12:00", "s": "4.5",
                           "d": "265", "g": "6.3", "f": "0,0"}]})
    rows = fetch_noaa(date(2026, 7, 1), date(2026, 7, 1), product="wind", session=s)
    assert rows[0]["value"] == 4.5
    assert rows[0]["wind_direction_degrees"] == 265
    assert rows[0]["wind_gust"] == 6.3
    assert s.requests[0][1]["interval"] == "h"
    assert "datum" not in s.requests[0][1]


def test_usgs_offset_paging_preserves_units_and_metadata():
    item = {"monitoring_location_id": "USGS-14246900", "parameter_code": "63680",
            "time": "2026-07-01T01:00:00Z", "value": "3.5",
            "unit_of_measure": "FNU", "approval_status": "Provisional",
            "time_series_id": "s1"}
    second = dict(item, time="2026-07-01T01:15:00+00:00", value=None)
    s = Session({"features": [{"properties": item}], "links": [{"rel": "next"}]},
                {"features": [{"properties": second}], "links": []})
    rows = fetch_usgs(date(2026, 7, 1), date(2026, 7, 1),
                      page_size=1, session=s)
    assert len(rows) == 2
    assert rows[0]["value"] == 3.5 and rows[1]["value"] is None
    assert rows[0]["timeseries_id"] == "s1"
    assert rows[0]["units"] == "FNU"
    assert s.requests[1][1]["offset"] == 1


def test_usgs_rejects_incorrect_station():
    item = {"monitoring_location_id": "USGS-00000000", "parameter_code": "63680",
            "time": "2026-07-01T00:00:00Z"}
    s = Session({"features": [{"properties": item}], "links": []})
    with pytest.raises(ValueError, match="Unexpected USGS"):
        fetch_usgs(date(2026, 7, 1), date(2026, 7, 1), session=s)


def test_range_restrictions_and_provider_errors():
    with pytest.raises(ValueError, match="28 days"):
        fetch_noaa(date(2026, 1, 1), date(2026, 2, 3))
    with pytest.raises(ValueError, match="Data provider error"):
        fetch_noaa(date(2026, 7, 1), date(2026, 7, 1),
                   session=Session({"error": {"message": "No data"}}))


def test_save_json_preserves_missing_values(tmp_path):
    p = save_json_csv([{"timestamp_utc": "2026-07-01T00:00:00+00:00",
                        "value": None}], tmp_path / "observations.json")
    assert json.loads(p.read_text())[0]["value"] is None
