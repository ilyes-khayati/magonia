import pytest
from pdf import make_pdf

from engine.assistant import Scripted, ToolCall, answer
from engine.fulltext import FullTextError
from engine.library import Library, Uploads

FIELD = (
    "Our field survey found that rainfed olive groves in Jendouba lost NDVI after the dry "
    "spring of 2023, while irrigated groves near the Medjerda kept their canopy green. " * 3
)
OTHER = "Wheat prices in the Beja market were recorded weekly by the cooperative. " * 4


@pytest.fixture
def mine(tmp_path):
    return Uploads(Library(tmp_path / "library.db"))


def test_an_uploaded_pdf_is_read_listed_and_removed(mine):
    added = mine.add("field_survey_2023.pdf", make_pdf([FIELD, OTHER]))
    assert added["id"] == "U1" and added["title"] == "field survey 2023"
    assert added["pages"] == 2 and added["passages"] >= 1
    assert [u["id"] for u in mine.all()] == ["U1"]
    assert mine.papers()[0].short == "field survey 2023"

    mine.remove("U1")
    assert mine.all() == []
    with pytest.raises(KeyError):
        mine.remove("U1")


def test_a_pdf_without_text_is_refused(mine):
    with pytest.raises(FullTextError):
        mine.add("scan.pdf", make_pdf([""]))


def test_only_files_that_speak_to_the_question_are_given(mine):
    mine.add("prices.pdf", make_pdf([OTHER]))
    mine.add("survey.pdf", make_pdf([FIELD]))
    papers, found = mine.relevant(
        "Did rainfed olive groves in Jendouba lose NDVI in 2023?", first=3
    )
    assert [p.title for p in papers] == ["survey"]
    assert {f.n for f in found} == {3}  # numbered after the papers already found


def test_magonia_cites_the_researchers_files_and_follows_their_instructions(tmp_path):
    shelf = Library(tmp_path / "library.db")
    Uploads(shelf).add("survey.pdf", make_pdf([FIELD]))
    model = Scripted(
        ToolCall("search_papers", {"query": "olive drought Jendouba"}),
        "Your survey found rainfed groves in Jendouba lost NDVI after the dry spring [1, p. 1].",
    )
    events = list(
        answer(
            model,
            [
                {
                    "role": "user",
                    "content": "What do studies say about olive NDVI in Jendouba in 2023?",
                }
            ],
            search=lambda query: [],
            library=shelf,
            judge=lambda claim, passage: "yes",
            instructions="Always answer in two sentences at most.",
        )
    )
    system = model.seen[0]["content"]
    assert "Always answer in two sentences at most." in system
    assert "[1] survey" in system and "[1, p. 1]" in system
    papers = next(e for e in events if e["type"] == "papers")["papers"]
    assert papers[0]["short"] == "survey" and papers[0]["venue"] == "Your library"
    check = events[-1]
    assert check["cited"] == [1] and check["pages_removed"] == []
    assert check["support"][0]["status"] == "supported"


def test_the_pdf_is_kept_once_by_its_content_and_can_be_restored(mine):
    pdf = make_pdf([FIELD])
    first = mine.add("survey.pdf", pdf)
    second = mine.add("survey copy.pdf", pdf)
    assert first["pdf"] and second["pdf"]
    kept = list(mine.library.files.iterdir())
    assert len(kept) == 1 and kept[0].read_bytes() == pdf  # the same bytes are stored once
    assert mine.pdf("U1") == kept[0]

    mine.remove("U1")
    assert [u["id"] for u in mine.all()] == ["U2"]
    assert [p.id for p in mine.papers()] == ["U2"]  # a removed file is not given to Mago
    assert mine.restore("U1")["title"] == "survey"
    assert [u["id"] for u in mine.all()] == ["U1", "U2"]


def test_a_file_removed_long_ago_is_deleted_for_good(tmp_path):
    shelf = Library(tmp_path / "library.db")
    mine = Uploads(shelf)
    mine.add("survey.pdf", make_pdf([FIELD]))
    mine.remove("U1")
    with shelf.connect() as db:
        db.execute("UPDATE uploads SET deleted = '2020-01-01 00:00:00'")
    Library(tmp_path / "library.db")  # opening the library purges
    assert list(shelf.files.iterdir()) == []
    with pytest.raises(KeyError):
        mine.restore("U1")
