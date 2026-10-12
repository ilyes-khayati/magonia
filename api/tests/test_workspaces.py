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


def test_deleting_a_workspace_deletes_its_areas(client, store):
    workspace = make_workspace(client)
    client.post(f"/workspaces/{workspace['id']}/areas", json={"name": "a", "geometry": SQUARE})
    client.delete(f"/workspaces/{workspace['id']}")
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
