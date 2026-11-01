from conftest import SQUARE

BOWTIE = {"type": "Polygon", "coordinates": [[[0, 0], [1, 1], [1, 0], [0, 1], [0, 0]]]}


def make_workspace(client, name="Jendouba"):
    return client.post("/workspaces", json={"name": name}).json()


def test_create_list_rename_delete(client):
    workspace = make_workspace(client)
    assert [w["name"] for w in client.get("/workspaces").json()] == ["Jendouba"]

    renamed = client.patch(f"/workspaces/{workspace['id']}", json={"name": "Orchards"}).json()
    assert renamed["name"] == "Orchards"

    assert client.delete(f"/workspaces/{workspace['id']}").status_code == 204
    assert client.get("/workspaces").json() == []
    assert client.get(f"/workspaces/{workspace['id']}").status_code == 404


def test_a_deleted_workspace_waits_in_recently_deleted(client):
    workspace = make_workspace(client)
    wid = workspace["id"]
    client.patch(f"/workspaces/{wid}", json={"settings": {"board": [1]}})
    client.delete(f"/workspaces/{wid}")

    [deleted] = client.get("/workspaces", params={"deleted": True}).json()
    assert deleted["name"] == "Jendouba" and deleted["deleted"]

    restored = client.post(f"/workspaces/{wid}/restore").json()
    assert restored["deleted"] is None
    assert client.get(f"/workspaces/{wid}").json()["settings"] == {"board": [1]}
    assert client.get("/workspaces", params={"deleted": True}).json() == []


def test_only_a_deleted_workspace_can_be_deleted_forever(client):
    wid = make_workspace(client)["id"]
    assert client.delete(f"/workspaces/{wid}", params={"forever": True}).status_code == 404
    client.delete(f"/workspaces/{wid}")
    assert client.delete(f"/workspaces/{wid}", params={"forever": True}).status_code == 204
    assert client.post(f"/workspaces/{wid}/restore").status_code == 404


def test_what_was_deleted_long_ago_is_purged(tmp_path):
    from api.store import Store

    store = Store(tmp_path / "m.db")
    wid = store.create_workspace("old")["id"]
    store.execute(
        "UPDATE workspaces SET deleted = '2020-01-01T00:00:00+00:00' WHERE id = ?", (wid,)
    )
    assert Store(tmp_path / "m.db").workspace(wid, deleted=True) is None


def test_areas_are_validated_measured_and_named(client):
    workspace = make_workspace(client)
    url = f"/workspaces/{workspace['id']}/areas"

    area = client.post(url, json={"name": "orchard", "geometry": SQUARE}).json()
    assert area["area_km2"] > 0.9

    duplicate = client.post(url, json={"name": "orchard", "geometry": SQUARE})
    assert duplicate.status_code == 409

    invalid = client.post(url, json={"name": "bowtie", "geometry": BOWTIE})
    assert invalid.status_code == 422
    assert "Self-intersection" in invalid.json()["detail"]

    assert client.patch(f"/areas/{area['id']}", json={"name": "olive"}).json()["name"] == "olive"
    assert [a["name"] for a in client.get(url).json()] == ["olive"]

    assert client.delete(f"/areas/{area['id']}").status_code == 204
    assert client.get(url).json() == []

    # deleted areas can be restored, until a new area takes the name
    assert client.post(f"/areas/{area['id']}/restore").json()["name"] == "olive"
    client.delete(f"/areas/{area['id']}")
    client.post(url, json={"name": "olive", "geometry": SQUARE})
    assert client.post(f"/areas/{area['id']}/restore").status_code == 404


def test_job_on_a_saved_area(client):
    workspace = make_workspace(client)
    area = client.post(
        f"/workspaces/{workspace['id']}/areas", json={"name": "orchard", "geometry": SQUARE}
    ).json()
    job = client.post(
        "/jobs", json={"area_id": area["id"], "start": "2023-01-01", "end": "2024-01-01"}
    ).json()
    assert job["status"] == "done"
    assert job["request"]["geometry"] == SQUARE


def test_reopening_restores_everything_without_recomputing(client, earth_engine):
    workspace = make_workspace(client)
    wid = workspace["id"]
    area = client.post(
        f"/workspaces/{wid}/areas", json={"name": "orchard", "geometry": SQUARE}
    ).json()
    client.post(
        "/jobs",
        json={
            "workspace_id": wid,
            "area_id": area["id"],
            "start": "2023-01-01",
            "end": "2024-01-01",
        },
    )
    settings = {"variable": "ndvi", "masking": "pixel", "selected_area": area["id"]}
    client.patch(f"/workspaces/{wid}", json={"settings": settings})
    calls = earth_engine.calls

    reopened = client.get(f"/workspaces/{wid}").json()
    assert reopened["settings"] == settings
    assert [a["name"] for a in reopened["areas"]] == ["orchard"]
    [job] = reopened["jobs"]
    assert len(job["result"]["points"]) == 3
    assert earth_engine.calls == calls  # nothing was recomputed


def test_deleting_a_workspace_forever_deletes_its_areas(client, store):
    workspace = make_workspace(client)
    client.post(f"/workspaces/{workspace['id']}/areas", json={"name": "a", "geometry": SQUARE})
    client.delete(f"/workspaces/{workspace['id']}")
    assert len(store.rows("SELECT * FROM areas")) == 1  # kept while it can be restored
    client.delete(f"/workspaces/{workspace['id']}", params={"forever": True})
    assert store.rows("SELECT * FROM areas") == []


def test_unknown_workspace_or_area(client):
    assert client.get("/workspaces/999").status_code == 404
    assert (
        client.post("/workspaces/999/areas", json={"name": "a", "geometry": SQUARE}).status_code
        == 404
    )
    assert client.patch("/areas/999", json={"name": "b"}).status_code == 404
    assert (
        client.post(
            "/jobs", json={"area_id": 999, "start": "2023-01-01", "end": "2024-01-01"}
        ).status_code
        == 404
    )


def test_ids_of_deleted_areas_are_never_reused(client):
    # The interface caches results by area; a reused id would show an old area's data
    workspace = make_workspace(client)
    url = f"/workspaces/{workspace['id']}/areas"
    first = client.post(url, json={"name": "a", "geometry": SQUARE}).json()
    client.delete(f"/areas/{first['id']}")
    second = client.post(url, json={"name": "b", "geometry": SQUARE}).json()
    assert second["id"] != first["id"]


def test_very_large_areas_are_refused_with_the_limit(client):
    workspace = make_workspace(client)
    huge = {"type": "Polygon", "coordinates": [[[0, 30], [3, 30], [3, 33], [0, 33], [0, 30]]]}
    response = client.post(
        f"/workspaces/{workspace['id']}/areas", json={"name": "region", "geometry": huge}
    )
    assert response.status_code == 422
    assert "limited to 10,000 km²" in response.json()["detail"]
