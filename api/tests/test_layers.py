from conftest import SQUARE

from api import main


def workspace_area(client):
    ws = client.post("/workspaces", json={"name": "Jendouba"}).json()["id"]
    return client.post(
        f"/workspaces/{ws}/areas", json={"name": "Orchard", "geometry": SQUARE}
    ).json()["id"]


def connected(monkeypatch):
    monkeypatch.setattr(main, "connect", lambda project=None: "test-project")


def test_a_month_is_drawn_once_and_then_served_from_memory(client, monkeypatch):
    connected(monkeypatch)
    main.TILES.clear()
    asked = []

    def tiles(key, month, scale=None):
        asked.append((key, month, scale))
        return {
            "url": "https://tiles/{z}/{x}/{y}",
            "month": month,
            "low": 0.0,
            "high": 0.9,
            "palette": ["#000"],
        }

    monkeypatch.setattr(main.layers, "tiles", tiles)
    first = client.get("/layers/ndvi/tiles", params={"month": "2020-03"})
    assert first.status_code == 200 and first.json()["url"] == "https://tiles/{z}/{x}/{y}"
    client.get("/layers/ndvi/tiles", params={"month": "2020-03"})
    assert asked == [("ndvi", "2020-03", None)]


def test_a_layer_needs_a_known_variable_a_month_and_for_spei_a_scale(client):
    assert client.get("/layers/olives/tiles", params={"month": "2020-03"}).status_code == 422
    assert client.get("/layers/ndvi/tiles", params={"month": "March"}).status_code == 422
    assert client.get("/layers/spei/tiles", params={"month": "2020-03"}).status_code == 422
    legend = client.get("/layers/spei/legend").json()
    assert (legend["low"], legend["high"]) == (-2.5, 2.5) and len(legend["palette"]) == 7


def test_earth_engine_failures_are_said(client, monkeypatch):
    connected(monkeypatch)
    main.TILES.clear()

    def refuse(*args, **kwargs):
        raise RuntimeError("quota exceeded")

    monkeypatch.setattr(main.layers, "tiles", refuse)
    reply = client.get("/layers/lst/tiles", params={"month": "2021-07"})
    assert reply.status_code == 502 and "quota exceeded" in reply.json()["detail"]


def test_a_point_is_read_once_and_kept(client, monkeypatch):
    connected(monkeypatch)
    calls = []

    def point_series(key, lon, lat, start, end, scale=None):
        calls.append((key, lon, lat))
        return [{"date": "2020-01-01", "value": 0.612345}, {"date": "2020-01-17", "value": None}]

    monkeypatch.setattr(main.layers, "point_series", point_series)
    body = {
        "variable": "ndvi",
        "lon": 8.5612345,
        "lat": 36.5085,
        "start": "2020-01-01",
        "end": "2020-02-01",
    }
    found = client.post("/inspect", json=body).json()
    assert found["pixel_m"] == 250 and found["lon"] == 8.56123
    assert found["points"] == [
        {"date": "2020-01-01", "value": 0.6123},
        {"date": "2020-01-17", "value": None},
    ]
    client.post("/inspect", json=body)
    assert len(calls) == 1
    assert client.post("/inspect", json={**body, "end": "2019-01-01"}).status_code == 422


def test_an_areas_pixels_are_outlined_and_kept(client, monkeypatch):
    connected(monkeypatch)
    area = workspace_area(client)
    grids = []

    def pixel_grid(key, geometry, limit=2000):
        grids.append(key)
        return {"features": [{"geometry": SQUARE, "properties": {"label": 1}}]}

    monkeypatch.setattr(main.layers, "pixel_grid", pixel_grid)
    found = client.get(f"/areas/{area}/pixels", params={"variable": "lst"}).json()
    assert found["pixel_m"] == 1000 and found["features"][0]["properties"] == {}
    client.get(f"/areas/{area}/pixels", params={"variable": "lst"})
    assert grids == ["lst"]
    assert client.get("/areas/999/pixels", params={"variable": "lst"}).status_code == 404
