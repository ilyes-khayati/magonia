import math

from conftest import SQUARE
from engine.pipeline import Request

from api.jobs import cache_key

WINDOW = {
    "start": "2018-01-01",
    "end": "2024-01-01",
    "variable": "spei",
    "scale": 3,
    "masking": "none",
}


def area(client):
    ws = client.post("/workspaces", json={"name": "Jendouba"}).json()["id"]
    return client.post(
        f"/workspaces/{ws}/areas", json={"name": "Orchard", "geometry": SQUARE}
    ).json()["id"]


def cache(store, months=72):
    """A cached native SPEI-3 series: a yearly cycle on a slow rise."""
    points = [
        {
            "date": f"{2018 + i // 12}-{i % 12 + 1:02d}-01",
            "value": 0.01 * i + math.sin(i * math.pi / 6),
        }
        | {"sd": None, "n_pixels": 1, "masked": False, "filled": False, "n_obs": 1, "n_valid": 1}
        for i in range(months)
    ]
    request = Request("spei", SQUARE, "2018-01-01", "2024-01-01", "none", 3, "native", 2)
    response = {"variable": "spei", "name": "SPEI-3", "units": "", "points": points}
    store.save_result(cache_key(request), response | {"warnings": [], "provenance": {}})


def test_a_cached_series_is_decomposed_with_the_sentences_magonia_reads(client, store):
    area_id = area(client)
    cache(store)
    reply = client.post(
        "/decomposition", json={**WINDOW, "area_id": area_id, "resolution": "native"}
    )
    assert reply.status_code == 200
    body = reply.json()
    assert (body["wavelet"], body["level"]) == ("dmey", 4)
    assert len(body["points"]) == 72
    first = body["points"][0]
    assert abs(first["trend"] + first["seasonal"] - first["value"]) < 1e-9
    assert body["summary"][0].startswith("Orchard, SPEI-3: the trend went from")


def test_a_series_not_extracted_yet_is_a_conflict(client):
    reply = client.post(
        "/decomposition", json={**WINDOW, "area_id": area(client), "resolution": "native"}
    )
    assert reply.status_code == 409


def test_only_native_series_are_decomposed(client):
    reply = client.post(
        "/decomposition", json={**WINDOW, "area_id": area(client), "resolution": "monthly"}
    )
    assert reply.status_code == 422


def test_too_short_a_series_is_refused_with_the_reason(client, store):
    area_id = area(client)
    cache(store, months=20)
    reply = client.post(
        "/decomposition", json={**WINDOW, "area_id": area_id, "resolution": "native"}
    )
    assert reply.status_code == 422 and "three years" in reply.json()["detail"]


def test_an_unknown_area_is_not_found(client):
    assert (
        client.post(
            "/decomposition", json={**WINDOW, "area_id": 99, "resolution": "native"}
        ).status_code
        == 404
    )
