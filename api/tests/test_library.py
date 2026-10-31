from engine.assistant import Scripted
from pdf import make_pdf

from api import main

SURVEY = "Rainfed olive groves in Jendouba lost NDVI after the dry spring of 2023. " * 5


def test_a_pdf_is_uploaded_listed_and_removed(client):
    added = client.post(
        "/library", files={"file": ("field_survey.pdf", make_pdf([SURVEY]), "application/pdf")}
    )
    assert added.status_code == 201
    assert added.json()["title"] == "field survey" and added.json()["pages"] == 1
    assert [f["id"] for f in client.get("/library").json()] == ["U1"]

    assert client.delete("/library/U1").status_code == 204
    assert client.get("/library").json() == []
    assert client.delete("/library/U1").status_code == 404


def test_what_is_not_a_readable_pdf_is_refused(client):
    page = client.post("/library", files={"file": ("notes.pdf", b"<html>", "application/pdf")})
    assert page.status_code == 400 and "not a PDF" in page.json()["detail"]
    scan = client.post("/library", files={"file": ("scan.pdf", make_pdf([""]), "application/pdf")})
    assert scan.status_code == 400 and "no text" in scan.json()["detail"]


def test_instructions_are_kept_per_workspace_and_given_to_magonia(client):
    ws = client.post("/workspaces", json={"name": "Jendouba"}).json()["id"]
    assert client.get(f"/workspaces/{ws}/instructions").json() == {"text": ""}
    saved = client.put(f"/workspaces/{ws}/instructions", json={"text": "Answer in French."})
    assert saved.json() == {"text": "Answer in French."}
    assert client.get(f"/workspaces/{ws}/instructions").json() == {"text": "Answer in French."}
    assert (
        client.put(f"/workspaces/{ws}/instructions", json={"text": "x" * 2001}).status_code == 422
    )

    model = Scripted("Bonjour.")
    main.app.dependency_overrides[main.get_provider] = lambda: model
    client.post(f"/workspaces/{ws}/chat", json={"content": "Hello"})
    assert "Answer in French." in model.seen[0]["content"]
