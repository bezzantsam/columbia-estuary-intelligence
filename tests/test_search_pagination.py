"""Offline Planet catalog pagination tests; no API key or network used."""
from datetime import date
import pytest
from estuary_intelligence.search import build_query, search_catalog


class Response:
    def __init__(self, data):
        self.data = data
    def raise_for_status(self):
        pass
    def json(self):
        return self.data


class Client:
    def __init__(self, first, *next_pages):
        self.first = first
        self.next_pages = list(next_pages)
        self.calls = []
    def post(self, url, *, params, auth, headers, json, timeout):
        self.calls.append(("post", url, params, auth))
        return Response(self.first)
    def get(self, url, *, auth, timeout):
        self.calls.append(("get", url, None, auth))
        return Response(self.next_pages.pop(0))


def scene(i):
    return {"id": f"scene{i}", "type": "PSScene",
            "properties": {"acquired": "2026-07-01T00:00:00Z"}}


def test_planet_follows_next_with_auth():
    first = {"features": [scene(1), scene(2)],
             "_links": {"_next": "https://api.planet.com/data/v1/searches/xx/results?_page=next"}}
    second = {"features": [scene(3)], "_links": {}}
    client = Client(first, second)
    query = build_query({"type": "Polygon", "coordinates": []},
                        date(2026, 7, 1), date(2026, 8, 1))
    out = search_catalog("fakekey", query, limit=5, page_size=2, session=client)
    assert [x["id"] for x in out["scenes"]] == ["scene1", "scene2", "scene3"]
    assert out["pages_fetched"] == 2 and not out["truncated"]
    assert client.calls[0][2]["_page_size"] == 2
    assert client.calls[1][3] == ("fakekey", "")


def test_planet_blocks_untrusted_pagination():
    client = Client({"features": [scene(1)],
                     "_links": {"_next": "https://example.com/steal"}})
    with pytest.raises(ValueError, match="Unsafe Planet"):
        search_catalog("fakekey", {}, limit=3, session=client)


def test_planet_fails_if_max_pages_hit():
    client = Client({"features": [scene(1)],
                     "_links": {"_next": "https://api.planet.com/more"}})
    with pytest.raises(RuntimeError, match="exceeded max_pages"):
        search_catalog("fakekey", {}, limit=3, page_size=1, max_pages=1,
                       session=client)


def test_planet_total_limit_is_not_page_size():
    first = {"features": [scene(1), scene(2)],
             "_links": {"_next": "https://api.planet.com/more"}}
    client = Client(first, {"features": [scene(3), scene(4)],
                            "_links": {"_next": "https://api.planet.com/page3"}})
    out = search_catalog("fakekey", {}, limit=3, page_size=2, session=client)
    assert out["count"] == 3 and out["truncated"]
