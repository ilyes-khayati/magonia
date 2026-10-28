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


def cache_monthly(store, variable, scale, values):
    points = [
        {"date": f"{2018 + i // 12}-{i % 12 + 1:02d}-01", "value": v}
        | {"sd": None, "n_pixels": 1, "masked": False, "filled": False, "n_obs": 1, "n_valid": 1}
        for i, v in enumerate(values)
    ]
    masking = "none" if variable == "spei" else "pixel"
    request = Request(variable, SQUARE, "2018-01-01", "2024-01-01", masking, scale, "monthly", 2)
    name = {"ndvi": "NDVI", "spei": f"SPEI-{scale}"}[variable]
    store.save_result(
        cache_key(request),
        {
            "variable": variable,
            "name": name,
            "units": "",
            "points": points,
            "warnings": [],
            "provenance": {},
        },
    )


def test_lags_describe_memory_and_a_driver_that_leads(client, store):
    area_id = area(client)
    wet = [math.sin(i * 1.3) + 0.3 * math.cos(i * 0.7) for i in range(72)]
    green = [
        0.5 + 0.1 * math.sin((i - 2) * 1.3) for i in range(72)
    ]  # follows SPEI two months later
    cache_monthly(store, "spei", 3, wet)
    cache_monthly(store, "ndvi", None, green)
    common = {
        "area_id": area_id,
        "start": "2018-01-01",
        "end": "2024-01-01",
        "resolution": "monthly",
    }
    body = {
        "response": {**common, "variable": "ndvi", "masking": "pixel"},
        "drivers": [{**common, "variable": "spei", "scale": 3, "masking": "none"}],
    }
    reply = client.post("/lags", json=body)
    assert reply.status_code == 200
    found = reply.json()
    assert len(found["acf"]) == 24
    assert (found["drivers"][0]["lag"], found["drivers"][0]["decision"]) == (2, "stands out")
    assert found["summary"][1].startswith("Orchard: SPEI-3 2 months earlier")


def test_lags_wait_for_their_series(client):
    common = {
        "area_id": area(client),
        "start": "2018-01-01",
        "end": "2024-01-01",
        "resolution": "monthly",
    }
    reply = client.post("/lags", json={"response": {**common, "variable": "ndvi"}})
    assert reply.status_code == 409
