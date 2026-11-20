"""Read-only pilot checks use synthetic metadata and never call Planet."""
from datetime import date
import json

import pytest
import requests

from estuary_intelligence.pilot import (
    ASSET_ROOT, PilotRequestError, list_scene_assets, main, run_pilot,
    summarize_assets,
)


AOI = {"type": "Polygon", "coordinates": [[
    [-124.17, 46.175], [-123.91, 46.175], [-123.91, 46.345],
    [-124.17, 46.345], [-124.17, 46.175],
]]}
START, END = date(2026, 7, 1), date(2026, 8, 1)
SCENE_ID = "20260718_191918_05_2475"
ACQUIRED = "2026-07-18T19:19:18.123456Z"


def asset(status="inactive", permissions=None):
    return {
        "status": status, "_permissions": ["download"] if permissions is None else permissions,
        "location": "https://example.com/imagery?token=NEVER_PERSIST_THIS",
        "_links": {"activate": "https://api.planet.com/activate?api_key=NEVER_PERSIST_THIS"},
    }


class Response:
    def __init__(self, payload, status=200):
        self.payload, self.status_code = payload, status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError("Do not persist response details or SECRET_API_KEY")

    def json(self):
        return self.payload


class Client:
    def __init__(self, assets, *, scene_count=1):
        self.assets = assets
        self.calls = []
        self.scene_count = scene_count

    def post(self, url, **kwargs):
        self.calls.append(("POST", url, kwargs))
        return Response({"features": [
            {"id": SCENE_ID if i == 0 else f"scene_{i}", "type": "Feature",
             "properties": {"item_type": "PSScene", "acquired": ACQUIRED, "cloud_cover": 0.02},
             "_links": {"thumbnail": "https://example.com?api_key=NEVER_PERSIST_THIS"}}
            for i in range(self.scene_count)
        ], "_links": {}})

    def get(self, url, **kwargs):
        self.calls.append(("GET", url, kwargs))
        return self.assets if isinstance(self.assets, Response) else Response(self.assets)


def test_inactive_downloadable_pair_is_not_an_active_download():
    result = summarize_assets({"ortho_analytic_8b_sr": asset(), "ortho_udm2": asset()})
    assert result["pair_download_permission_confirmed"] is True
    assert result["both_assets_active"] is False
    assert result["readiness"] == "permissions_confirmed_activation_needed"


def test_active_assets_without_permissions_are_not_authorized():
    result = summarize_assets({"ortho_analytic_8b_sr": asset("active", []), "ortho_udm2": asset("active")})
    assert result["both_assets_active"] is True
    assert result["pair_download_permission_confirmed"] is False
    assert result["readiness"] == "download_not_authorized"


def test_four_band_fallback_preserves_permission_and_removes_urls():
    result = summarize_assets({
        "ortho_analytic_8b_sr": asset("active", []),
        "ortho_analytic_4b_sr": asset("active"), "ortho_udm2": asset("active"),
    })
    assert result["selected_surface_reflectance_asset"] == "ortho_analytic_4b_sr"
    assert result["readiness"] == "permissions_confirmed_assets_active"
    assert "NEVER_PERSIST_THIS" not in json.dumps(result)
    assert "location" not in json.dumps(result)


def test_missing_mask_and_missing_permission_remain_distinct():
    missing = summarize_assets({"ortho_analytic_8b_sr": asset()})
    unknown = summarize_assets({"ortho_analytic_8b_sr": {"status": "inactive"}, "ortho_udm2": asset()})
    assert missing["readiness"] == "missing_required_assets"
    assert unknown["readiness"] == "download_permission_unconfirmed"


def test_dry_run_requires_no_key_or_network_and_cli_writes_plan(tmp_path, monkeypatch):
    monkeypatch.delenv("PL_API_KEY", raising=False)
    monkeypatch.setattr("estuary_intelligence.pilot.search_catalog", lambda *a, **k: pytest.fail("network search attempted"))
    aoi = tmp_path / "aoi.geojson"
    aoi.write_text(json.dumps(AOI))
    output = tmp_path / "plan.json"
    main(["--start", START.isoformat(), "--end", END.isoformat(), "--aoi", str(aoi),
          "--limit", "3", "--dry-run", "--output", str(output)])
    result = json.loads(output.read_text())
    assert result["mode"] == "dry_run"
    assert result["catalog"]["executed"] is False
    assert result["plan"]["max_asset_metadata_requests"] == 3
    assert result["access_expiration"]["verified"] is False
    assert result["scenes"] == []


def test_live_check_is_bounded_metadata_only_and_preserves_timestamp():
    client = Client({"ortho_analytic_8b_sr": asset("active"), "ortho_udm2": asset("active")}, scene_count=4)
    result = run_pilot(aoi=AOI, start=START, end=END, api_key="SECRET_API_KEY", limit=2, session=client)
    assert result["summary"]["scenes_inspected"] == 2
    assert result["scenes"][0]["acquired"] == ACQUIRED
    assert len(client.calls) == 3  # One quick search, two asset metadata reads.
    assert client.calls[0][0:2] == ("POST", "https://api.planet.com/data/v1/quick-search")
    for method, url, kwargs in client.calls[1:]:
        assert method == "GET" and url.startswith(ASSET_ROOT + "/") and url.endswith("/assets")
        assert kwargs["allow_redirects"] is False
    serialized = json.dumps(result)
    assert "SECRET_API_KEY" not in serialized and "NEVER_PERSIST_THIS" not in serialized
    assert result["plan"]["imagery_downloaded"] is False
    assert result["access_expiration"]["end_date"] is None


@pytest.mark.parametrize("status", [302, 401, 403, 429, 500])
def test_http_failures_do_not_follow_redirects_or_leak_response(status):
    client = Client(Response({"error": "SECRET_API_KEY"}, status))
    with pytest.raises(PilotRequestError, match=f"^asset_http_{status}$"):
        list_scene_assets("SECRET_API_KEY", SCENE_ID, session=client)
    assert len(client.calls) == 1
    assert client.calls[0][2]["allow_redirects"] is False


def test_catalog_visibility_with_forbidden_assets_is_recorded():
    client = Client(Response({"error": "SECRET_API_KEY"}, 403))
    result = run_pilot(aoi=AOI, start=START, end=END, api_key="SECRET_API_KEY", session=client)
    scene = result["scenes"][0]
    assert scene["catalog_visible"] is True
    assert scene["inspection_status"] == "failed"
    assert scene["error_code"] == "asset_http_403"
    assert result["summary"]["pairs_with_download_permission"] == 0
    assert "SECRET_API_KEY" not in json.dumps(result)


def test_auth_failure_stops_remaining_asset_requests():
    client = Client(Response({}, 401), scene_count=5)
    result = run_pilot(aoi=AOI, start=START, end=END, api_key="SECRET_API_KEY", limit=5, session=client)
    assert len(client.calls) == 2
    assert result["summary"]["inspection_failures"] == 1


def test_transport_failure_does_not_expose_exception_details():
    class BrokenClient:
        def get(self, *args, **kwargs):
            raise requests.ConnectionError("SECRET_API_KEY at https://example.com/private")

    with pytest.raises(PilotRequestError, match="^asset_request_failed$"):
        list_scene_assets("SECRET_API_KEY", SCENE_ID, session=BrokenClient())


def test_cli_partial_failure_writes_evidence_and_exits_nonzero(tmp_path, monkeypatch, capsys):
    client = Client(Response({"error": "SECRET_API_KEY"}, 403))
    manifest = run_pilot(aoi=AOI, start=START, end=END, api_key="SECRET_API_KEY", session=client)
    monkeypatch.setattr("estuary_intelligence.pilot.run_pilot", lambda **kwargs: manifest)
    aoi = tmp_path / "aoi.geojson"
    aoi.write_text(json.dumps(AOI))
    output = tmp_path / "pilot.json"
    with pytest.raises(SystemExit) as exc:
        main(["--start", START.isoformat(), "--end", END.isoformat(),
              "--aoi", str(aoi), "--output", str(output)])
    assert exc.value.code == 1
    assert json.loads(output.read_text())["scenes"][0]["error_code"] == "asset_http_403"
    captured = capsys.readouterr()
    assert "SECRET_API_KEY" not in captured.out + captured.err


@pytest.mark.parametrize("limit", [0, -1, 21, True, 1.5])
def test_invalid_bounds_fail_before_requests(limit):
    with pytest.raises(ValueError, match="limit"):
        run_pilot(aoi=AOI, start=START, end=END, limit=limit, dry_run=True)


def test_invalid_dates_and_missing_key_fail_before_requests():
    with pytest.raises(ValueError, match="End date"):
        run_pilot(aoi=AOI, start=END, end=START, dry_run=True)
    with pytest.raises(ValueError, match="PL_API_KEY"):
        run_pilot(aoi=AOI, start=START, end=END)


@pytest.mark.parametrize("scene_id", ["../steal", "https://example.com/", "a?api_key=secret", ""])
def test_scene_id_cannot_change_origin_or_endpoint(scene_id):
    client = Client({})
    with pytest.raises(ValueError, match="Invalid PlanetScope"):
        list_scene_assets("SECRET_API_KEY", scene_id, session=client)
    assert client.calls == []
