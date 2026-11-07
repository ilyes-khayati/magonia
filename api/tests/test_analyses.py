import math

from conftest import SQUARE
from engine.assistant import Scripted
from engine.pipeline import Request

from api.jobs import cache_key

WINDOW = {
    "start": "2018-01-01",
    "end": "2024-01-01",
    "variable": "spei",
    "scale": 3,
    "masking": "none",
}


def conversation(client, ws):
    return client.post(f"/workspaces/{ws}/conversations").json()["id"]


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
    name = {"ndvi": "NDVI", "lst": "LST", "spei": f"SPEI-{scale}"}[variable]
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


def cache_years(store, variable, scale, values, start_year=2005):
    """A cached monthly series of len(values) months from January of start_year."""
    points = [
        {"date": f"{start_year + i // 12}-{i % 12 + 1:02d}-01", "value": v}
        | {"sd": None, "n_pixels": 1, "masked": False, "filled": False, "n_obs": 1, "n_valid": 1}
        for i, v in enumerate(values)
    ]
    end = f"{start_year + len(values) // 12}-01-01"
    masking = "none" if variable == "spei" else "pixel"
    request = Request(variable, SQUARE, f"{start_year}-01-01", end, masking, scale, "monthly", 2)
    name = {"ndvi": "NDVI", "lst": "LST", "spei": f"SPEI-{scale}"}[variable]
    response = {"variable": variable, "name": name, "units": "", "points": points}
    store.save_result(cache_key(request), response | {"warnings": [], "provenance": {}})
    return {
        "start": f"{start_year}-01-01",
        "end": end,
        "resolution": "monthly",
        "variable": variable,
    }


def test_models_fit_in_the_background_then_answer_from_the_cache(client, store, monkeypatch):
    from api import main

    monkeypatch.setattr(main, "forecast", fake_forecast := FakeForecast())
    area_id = area(client)
    ndvi = cache_years(store, "ndvi", None, [0.5 + 0.2 * math.sin(i / 1.9) for i in range(180)])
    body = {"response": {**ndvi, "area_id": area_id, "masking": "pixel"}, "own_lags": [1, 12]}

    first = client.post("/models", json=body)  # the test runner fits at once
    assert first.status_code == 202 and first.json() == {"status": "running"}
    second = client.post("/models", json=body)
    assert second.status_code == 200
    assert second.json()["status"] == "done" and second.json()["summary"] == ["Orchard: fitted."]
    assert fake_forecast.calls == 1  # the second answer came from the cache


def test_a_forecast_that_cannot_be_made_says_why(client, store, monkeypatch):
    from engine.models import ForecastError

    from api import main

    def refuse(*args, **kwargs):
        raise ForecastError("A forecast needs 8 years to train")

    monkeypatch.setattr(main, "forecast", refuse)
    ndvi = cache_years(store, "ndvi", None, [0.5] * 24)
    body = {"response": {**ndvi, "area_id": area(client), "masking": "pixel"}}
    client.post("/models", json=body)
    assert client.post("/models", json=body).json() == {
        "status": "failed",
        "error": "A forecast needs 8 years to train",
    }


class FakeForecast:
    """Stands in for the engine's forecast, which is tested there, and counts its calls."""

    def __init__(self):
        self.calls = 0
        self.choices = {}

    def __call__(self, area, *args, **kwargs):
        self.calls += 1
        self.choices = kwargs

        class Found:
            def to_dict(self):
                return {
                    "summary": [f"{area}: fitted."],
                    "models": [],
                    "baselines": {"persistence": {"RMSE": 0.1}, "climatology": {"RMSE": 0.1}},
                    "observed": [0.5] * 36,
                }

        return Found()


def test_magonia_reads_a_finished_forecast(client, store, monkeypatch):
    from api import main

    monkeypatch.setattr(main, "forecast", FakeForecast())
    model = Scripted("Fine.")
    main.app.dependency_overrides[main.get_provider] = lambda: model
    area_id = area(client)
    ndvi = cache_years(store, "ndvi", None, [0.5] * 180)
    series = {**ndvi, "area_id": area_id, "masking": "pixel"}
    client.post("/models", json={"response": series})
    analysis = {"id": 1, "kind": "models", "response": "ndvi", "drivers": []}
    view = {"charts": [], "analyses": [analysis], "series": [series]}
    ws = client.get("/workspaces").json()[0]["id"]
    client.post(
        f"/conversations/{conversation(client, ws)}/chat",
        json={"content": "Which model won?", "view": view},
    )
    assert "[Models 1: NDVI forecast]\n- Orchard: fitted." in model.seen[-1]["content"]


def test_magonia_reads_an_experiment_by_its_name_and_area(client, store, monkeypatch):
    from api import main

    monkeypatch.setattr(main, "forecast", FakeForecast())
    model = Scripted("Fine.")
    main.app.dependency_overrides[main.get_provider] = lambda: model
    area_id = area(client)
    ndvi = cache_years(store, "ndvi", None, [0.5] * 180)
    series = {**ndvi, "area_id": area_id, "masking": "pixel"}
    client.post("/models", json={"response": series, "models": ["Ridge"], "calendar": False})
    experiment = {
        "kind": "models",
        "name": "Ridge alone",
        "area": area_id,
        "response": "ndvi",
        "drivers": [],
        "own_lags": None,
        "driver_lags": None,
        "test_years": 3,
        "models": ["Ridge"],
        "params": {},
        "calendar": False,
        "rolling": True,
    }
    elsewhere = {**experiment, "name": "Elsewhere", "area": area_id + 1}
    view = {"charts": [], "analyses": [experiment, elsewhere], "series": [series]}
    ws = client.get("/workspaces").json()[0]["id"]
    client.post(
        f"/conversations/{conversation(client, ws)}/chat",
        json={"content": "How did Ridge do?", "view": view},
    )
    assert "[Ridge alone: NDVI forecast]\n- Orchard: fitted." in model.seen[-1]["content"]
    assert "Elsewhere" not in model.seen[-1]["content"]


def test_explanations_need_fitted_models_then_run_in_the_background(client, store, monkeypatch):
    from api import main

    class Found:
        def to_dict(self):
            return {"importance": {}, "families": {}, "agreement": [], "seeds": 5}

    monkeypatch.setattr(main, "forecast", FakeForecast())
    monkeypatch.setattr(main, "explain", lambda X, y, params: Found())
    monkeypatch.setattr(main, "describe", lambda area, found: [f"{area}: explained."])
    ndvi = cache_years(store, "ndvi", None, [0.5 + 0.1 * math.sin(i) for i in range(180)])
    body = {"response": {**ndvi, "area_id": area(client), "masking": "pixel"}, "own_lags": [1]}

    assert client.post("/explanations", json=body).status_code == 409  # no models yet
    client.post("/models", json=body)
    assert client.post("/explanations", json=body).json() == {"status": "running"}
    done = client.post("/explanations", json=body).json()
    assert done["status"] == "done" and done["summary"] == ["Orchard: explained."]


def test_models_and_their_settings_are_the_researchers_choice(client, store, monkeypatch):
    from api import main

    monkeypatch.setattr(main, "forecast", fake_forecast := FakeForecast())
    ndvi = cache_years(store, "ndvi", None, [0.5 + 0.2 * math.sin(i / 1.9) for i in range(180)])
    base = {"response": {**ndvi, "area_id": area(client), "masking": "pixel"}, "own_lags": [1]}
    chosen = {
        **base,
        "models": ["XGBoost"],
        "params": {"XGBoost": {"max_depth": 3}},
        "calendar": False,
        "rolling": False,
    }
    client.post("/models", json=chosen)
    assert fake_forecast.choices == {
        "models": ["XGBoost"],
        "params": {"XGBoost": {"max_depth": 3.0}},
        "calendar": False,
        "rolling": False,
    }
    # earlier forecasts keep their key: the defaults, written out or not, are the same choice
    defaults = {**base, "models": ["Ridge", "RandomForest", "XGBoost"], "calendar": True}
    key = main.models_key(main.ModelsRequest(**base), store)
    assert main.models_key(main.ModelsRequest(**defaults), store) == key
    assert main.models_key(main.ModelsRequest(**chosen), store) != key
    unused = {**base, "params": {}, "rolling": True}
    assert main.models_key(main.ModelsRequest(**unused), store) == key
    other_model = {**chosen, "params": {"XGBoost": {"max_depth": 3}, "Ridge": {"alpha": 1}}}
    assert main.models_key(main.ModelsRequest(**other_model), store) == main.models_key(
        main.ModelsRequest(**chosen), store
    )
    assert client.post("/models", json={**base, "models": []}).status_code == 422


def test_cards_carry_the_guardrails_cautions(client, store, monkeypatch):
    from api import main

    monkeypatch.setattr(main, "forecast", FakeForecast())
    area_id = area(client)
    seasonal = [0.5 + 0.3 * math.sin(2 * math.pi * i / 12) for i in range(180)]
    ndvi = cache_years(store, "ndvi", None, seasonal)
    lst = cache_years(
        store, "lst", None, [20 - 10 * math.sin(2 * math.pi * i / 12) for i in range(180)]
    )
    body = {
        "response": {**ndvi, "area_id": area_id, "masking": "pixel"},
        "drivers": [{**lst, "area_id": area_id, "masking": "pixel"}],
        "deseasonalise": False,
    }
    lagged = client.post("/lags", json=body).json()
    assert any("the seasonal cycle was kept" in c for c in lagged["cautions"])
    assert client.post("/lags", json={**body, "deseasonalise": True}).json()["cautions"] == []

    models = {"response": body["response"], "own_lags": [1]}
    client.post("/models", json=models)
    assert client.post("/models", json=models).json()["cautions"] == []


def test_stability_needs_fitted_models_then_runs_in_the_background(client, store, monkeypatch):
    from api import main

    class Held:
        def to_dict(self):
            return {"windows": [], "leading": {}, "summary": ["Orchard: stable."]}

    monkeypatch.setattr(main, "forecast", FakeForecast())
    monkeypatch.setattr(main, "stability", lambda *args, **kwargs: Held())
    ndvi = cache_years(store, "ndvi", None, [0.5 + 0.1 * math.sin(i) for i in range(180)])
    body = {"response": {**ndvi, "area_id": area(client), "masking": "pixel"}, "own_lags": [1]}

    assert client.post("/stability", json=body).status_code == 409  # no models yet
    client.post("/models", json=body)
    assert client.post("/stability", json=body).json() == {"status": "running"}
    done = client.post("/stability", json=body).json()
    assert done["status"] == "done" and done["summary"] == ["Orchard: stable."]


def test_findings_follow_an_area_renamed_after_they_ran(client, store, monkeypatch):
    from api import main

    class Held:
        def to_dict(self):
            return {"windows": [], "leading": {}, "summary": ["Orchard: stable."]}

    monkeypatch.setattr(main, "forecast", FakeForecast())
    monkeypatch.setattr(main, "explain", lambda X, y, params: Explained())
    monkeypatch.setattr(main, "describe", lambda area, found: [f"{area}: explained."])
    monkeypatch.setattr(main, "stability", lambda *args, **kwargs: Held())
    ndvi = cache_years(store, "ndvi", None, [0.5 + 0.1 * math.sin(i) for i in range(180)])
    area_id = area(client)
    body = {"response": {**ndvi, "area_id": area_id, "masking": "pixel"}, "own_lags": [1]}
    for path in ("/models", "/explanations", "/stability"):
        client.post(path, json=body)

    client.patch(f"/areas/{area_id}", json={"name": "Grove"})
    assert client.post("/models", json=body).json()["summary"] == ["Grove: fitted."]
    assert client.post("/explanations", json=body).json()["summary"] == ["Grove: explained."]
    assert client.post("/stability", json=body).json()["summary"] == ["Grove: stable."]


def test_a_forecast_stored_without_its_area_name_is_still_renamed():
    from api.main import under_current_name

    lines = ["Orchard: fitted.", "Orchard: tested."]
    assert under_current_name(lines, {}, "Grove") == ["Grove: fitted.", "Grove: tested."]


class Explained:
    def to_dict(self):
        return {"importance": {}, "families": {}, "agreement": [], "seeds": 5}


def test_a_trend_is_tested_on_annual_means(client, store):
    rising = [0.4 + 0.01 * (i // 12) + 0.2 * math.sin(2 * math.pi * i / 12) for i in range(180)]
    ndvi = cache_years(store, "ndvi", None, rising)
    found = client.post("/trend", json={**ndvi, "area_id": area(client), "masking": "pixel"}).json()
    assert round(found["slope"], 3) == 0.1 and found["p"] < 0.001
    assert found["summary"][0].startswith("Orchard, NDVI: annual means rising by +0.100 per decade")


def test_season_dates_need_ndvi_at_its_own_step(client, store):
    ndvi = cache_years(store, "ndvi", None, [0.5] * 60)
    body = {**ndvi, "area_id": area(client), "masking": "pixel"}
    assert client.post("/phenology", json=body).status_code == 422  # monthly, not native


def test_an_analysis_is_exported_as_a_notebook_with_its_data(client, store):
    ndvi = cache_years(store, "ndvi", None, [0.5 + 0.2 * math.sin(i / 1.9) for i in range(36)])
    body = {
        "title": "Orchard trend",
        "kind": "trend",
        "series": [{**ndvi, "area_id": area(client), "masking": "pixel"}],
    }
    reply = client.post("/notebook", json=body)
    assert reply.status_code == 200
    assert reply.headers["content-disposition"] == 'attachment; filename="orchard-trend.ipynb"'
    nb = reply.json()
    assert nb["nbformat"] == 4 and nb["metadata"]["magonia"]["kind"] == "trend"
    sources = ["".join(c["source"]) for c in nb["cells"]]
    assert any("MODIS Terra MOD13Q1" in s for s in sources)
    assert any("from engine.trend import trend" in s for s in sources)


def test_magonia_reads_what_the_researcher_pinned_first(client, store):
    from api import main

    model = Scripted("Fine.")
    main.app.dependency_overrides[main.get_provider] = lambda: model
    area(client)
    view = {
        "charts": [],
        "analyses": [],
        "series": [],
        "board": [{"title": "Note: check 2017", "text": "The 2017 dip may be the drought."}],
    }
    ws = client.get("/workspaces").json()[0]["id"]
    client.post(
        f"/conversations/{conversation(client, ws)}/chat",
        json={"content": "What did I note?", "view": view},
    )
    assert (
        "[Board: Note: check 2017]\n- The 2017 dip may be the drought." in model.seen[-1]["content"]
    )
