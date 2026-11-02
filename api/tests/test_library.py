from engine.assistant import Scripted
from pdf import make_pdf

from api import main

SURVEY = "Rainfed olive groves in Jendouba lost NDVI after the dry spring of 2023. " * 5


def conversation(client, ws):
    return client.post(f"/workspaces/{ws}/conversations").json()["id"]


def workspace(client, name="Jendouba"):
    return client.post("/workspaces", json={"name": name}).json()["id"]


def test_a_pdf_is_uploaded_listed_and_removed(client):
    ws = workspace(client)
    added = client.post(
        f"/workspaces/{ws}/library",
        files={"file": ("field_survey.pdf", make_pdf([SURVEY]), "application/pdf")},
    )
    assert added.status_code == 201
    assert added.json()["title"] == "field survey" and added.json()["pages"] == 1
    assert [f["id"] for f in client.get(f"/workspaces/{ws}/library").json()] == ["U1"]

    assert client.delete("/library/U1").status_code == 204
    assert client.get(f"/workspaces/{ws}/library").json() == []
    assert client.delete("/library/U1").status_code == 404


def test_a_kept_pdf_is_shown_and_a_removed_file_restored(client):
    ws = workspace(client)
    pdf = make_pdf([SURVEY, SURVEY])
    client.post(
        f"/workspaces/{ws}/library", files={"file": ("field_survey.pdf", pdf, "application/pdf")}
    )
    shown = client.get("/library/U1/pdf")
    assert shown.status_code == 200 and shown.content == pdf
    assert shown.headers["content-type"] == "application/pdf"
    assert shown.headers["content-disposition"].startswith("inline")

    client.delete("/library/U1")
    assert client.get("/library/U1/pdf").status_code == 404
    assert client.post("/library/U1/restore").json()["pdf"] is True
    assert [f["id"] for f in client.get(f"/workspaces/{ws}/library").json()] == ["U1"]
    assert client.post("/library/U9/restore").status_code == 404


def test_what_is_not_a_readable_pdf_is_refused(client):
    ws = workspace(client)
    page = client.post(
        f"/workspaces/{ws}/library", files={"file": ("notes.pdf", b"<html>", "application/pdf")}
    )
    assert page.status_code == 400 and "not a PDF" in page.json()["detail"]
    scan = client.post(
        f"/workspaces/{ws}/library", files={"file": ("scan.pdf", make_pdf([""]), "application/pdf")}
    )
    assert scan.status_code == 400 and "no text" in scan.json()["detail"]


def test_instructions_are_kept_per_workspace_and_given_to_magonia(client):
    ws = workspace(client)
    assert client.get(f"/workspaces/{ws}/instructions").json() == {"text": ""}
    saved = client.put(f"/workspaces/{ws}/instructions", json={"text": "Answer in French."})
    assert saved.json() == {"text": "Answer in French."}
    assert client.get(f"/workspaces/{ws}/instructions").json() == {"text": "Answer in French."}
    assert (
        client.put(f"/workspaces/{ws}/instructions", json={"text": "x" * 2001}).status_code == 422
    )

    model = Scripted("Bonjour.")
    main.app.dependency_overrides[main.get_provider] = lambda: model
    client.post(f"/conversations/{conversation(client, ws)}/chat", json={"content": "Hello"})
    assert "Answer in French." in model.seen[0]["content"]


def test_each_workspace_has_its_own_files_and_magonia_sees_only_those(client):
    jendouba, sfax = workspace(client), workspace(client, "Sfax")
    survey = ("field_survey.pdf", make_pdf([SURVEY]), "application/pdf")
    client.post(f"/workspaces/{jendouba}/library", files={"file": survey})
    assert [f["title"] for f in client.get(f"/workspaces/{jendouba}/library").json()] == [
        "field survey"
    ]
    assert client.get(f"/workspaces/{sfax}/library").json() == []
    assert client.get("/workspaces/999/library").status_code == 404

    model = Scripted("You have not added any files here.")
    main.app.dependency_overrides[main.get_provider] = lambda: model
    client.post(
        f"/conversations/{conversation(client, sfax)}/chat",
        json={"content": "Which files have I added?"},
    )
    assert "field survey" not in model.seen[0]["content"]
