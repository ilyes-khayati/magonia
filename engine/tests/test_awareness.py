from pdf import make_pdf

from engine.assistant import Scripted, answer
from engine.awareness import (
    asks_about_own_files,
    earlier_papers,
    files_asked_about,
    listing,
    restated,
    wants_literature,
)
from engine.library import Library, Uploads

FINDINGS = (
    "Abstract. NDVI of rainfed olive groves near Sfax fell 18 percent in the 2022 drought, "
    "while irrigated groves lost 6 percent. "
)
METHODS = "Methods. MODIS MOD13Q1 composites were averaged over 40 groves for 2015 to 2023. " * 3
FILES = [
    {
        "id": "U1",
        "title": "Sfax drought",
        "filename": "sfax_drought.pdf",
        "pages": 9,
        "added": "2026-10-31 10:00:00",
    },
    {
        "id": "U2",
        "title": "Beja field notes",
        "filename": "beja-notes.pdf",
        "pages": 1,
        "added": "2026-10-30 08:00:00",
    },
]


def test_questions_about_the_researchers_own_files_are_recognised():
    for asked in (
        "What are the key findings of the paper I uploaded?",
        "Which files have I added?",
        "Summarise my notes",
        "what does the PDF say about irrigation?",
        "Is there anything in my library about Sfax?",
    ):
        assert asks_about_own_files(asked), asked
    for asked in ("What does drought do to olive NDVI?", "Add a trend analysis", "my areas"):
        assert not asks_about_own_files(asked), asked


def test_files_are_found_by_name_or_by_speaking_of_ones_own():
    assert files_asked_about("What does Sfax drought say?", FILES) == FILES[:1]
    assert files_asked_about("open beja_notes please", FILES) == []  # not its name
    assert files_asked_about("what is in beja-notes.pdf?", FILES) == FILES[1:]
    assert files_asked_about("the paper I uploaded", FILES) == FILES
    assert files_asked_about("What is NDVI?", FILES) == []


def test_files_are_found_by_their_place_in_the_library():
    assert files_asked_about("What's in the second file?", FILES) == FILES[1:]
    assert files_asked_about("summarise my latest upload", FILES) == FILES[1:]
    assert files_asked_about("the first paper and the last PDF", FILES) == FILES
    assert files_asked_about("the fifth file", FILES) == []  # there is no fifth
    assert files_asked_about("the first study you cited", FILES) == []


def test_literature_is_still_searched_when_asked_for():
    assert wants_literature("How does my file compare with the published literature?")
    assert not wants_literature("What are the key findings of the paper I uploaded?")


def test_the_library_is_listed_for_the_model():
    said = listing(FILES)
    assert "holds 2 files" in said
    assert "- Sfax drought (sfax_drought.pdf, 9 pages, added 31 October 2026)" in said
    assert "Beja field notes (beja-notes.pdf, 1 page," in said
    assert "is empty" in listing([])


ANSWER = {
    "role": "assistant",
    "content": "Rainfed groves lost NDVI [1, p. 6], unlike irrigated ones [2].",
    "papers": [
        {
            "n": 1,
            "id": "W1",
            "title": "Drought and olives",
            "authors": ["A Sghaier"],
            "year": 2022,
            "venue": None,
            "doi": None,
            "abstract": "Rainfed groves lost NDVI.",
            "open_access_url": None,
            "cited_by": 3,
            "countries": [],
            "short": "Sghaier, 2022",
        },
        {
            "n": 2,
            "id": "W2",
            "title": "Irrigation",
            "authors": ["B Crespo"],
            "year": 2025,
            "venue": None,
            "doi": None,
            "abstract": None,
            "open_access_url": None,
            "cited_by": 0,
            "countries": [],
            "short": "Crespo, 2025",
        },
        {
            "n": 3,
            "id": "W3",
            "title": "Not cited",
            "authors": [],
            "year": None,
            "venue": None,
            "doi": None,
            "abstract": None,
            "open_access_url": None,
            "cited_by": 0,
            "countries": [],
        },
    ],
    "cited": [1, 2],
}


def test_earlier_citations_become_names_since_numbers_start_again():
    [user, assistant] = restated([{"role": "user", "content": "Drought?"}, ANSWER])
    assert user == {"role": "user", "content": "Drought?"}
    assert assistant["content"] == (
        "Rainfed groves lost NDVI (Sghaier, 2022, p. 6), unlike irrigated ones (Crespo, 2025)."
    )
    assert set(assistant) == {"role", "content"}  # nothing else reaches the model


def test_the_papers_cited_earlier_are_carried_over_latest_first():
    later = {**ANSWER, "papers": ANSWER["papers"][1:2], "cited": [2]}
    found = earlier_papers([ANSWER, {"role": "user", "content": "more"}, later])
    assert [p.id for p in found] == ["W2", "W1"]  # not repeated, uncited ones left out
    assert found[1].short == "Sghaier, 2022"


class Offered(Scripted):
    """Also records which tools the model was offered at each call."""

    def __init__(self, *steps):
        super().__init__(*steps)
        self.offered = []

    def stream(self, messages, tools=None):
        self.offered.append([t["function"]["name"] for t in tools or []])
        yield from super().stream(messages, tools)


def test_a_question_about_an_uploaded_paper_reads_it_without_searching(tmp_path):
    shelf = Library(tmp_path / "library.db")
    Uploads(shelf).add("sfax_drought.pdf", make_pdf([FINDINGS, METHODS]))
    model = Offered("Your paper found an 18 percent fall [1, p. 1].")
    events = list(
        answer(
            model,
            [{"role": "user", "content": "What are the key findings of the paper I uploaded?"}],
            search=lambda q: [],
            library=shelf,
        )
    )
    assert model.offered == [[]]  # no search: the answer is in their file
    [papers] = [e for e in events if e["type"] == "papers"]
    assert papers["papers"][0]["title"] == "sfax drought"
    [passages] = [e for e in events if e["type"] == "passages"]
    assert passages["passages"][0]["text"].startswith("Abstract.")  # its opening is given
    system = model.seen[0]["content"]
    assert "holds 1 file:" in system and "sfax drought (sfax_drought.pdf, 2 pages" in system
    # its passages come right before the question, not at the end of the rules
    asked = model.seen[-1]["content"]
    assert "18 percent" not in system
    assert asked.index("18 percent") < asked.index("The researcher asks: What are the key")
    assert events[-1]["text"] == "Your paper found an 18 percent fall [1, p. 1]."


def test_magonia_can_say_which_files_there_are_even_in_small_talk(tmp_path):
    shelf = Library(tmp_path / "library.db")
    model = Scripted("You have not added any files yet.")
    list(
        answer(model, [{"role": "user", "content": "hi! which files have I added?"}], library=shelf)
    )
    assert "is empty: they have not added any files" in model.seen[0]["content"]


def test_a_follow_up_can_cite_the_papers_of_the_earlier_answer(tmp_path):
    model = Scripted("The first was Sghaier [1], on rainfed groves.")
    events = list(
        answer(
            model,
            [
                {"role": "user", "content": "What does drought do?"},
                ANSWER,
                {"role": "user", "content": "Tell me more about the first study you cited"},
            ],
            search=lambda q: [],
        )
    )
    first = next(e for e in events if e["type"] == "papers")
    assert [p["id"] for p in first["papers"]] == ["W1", "W2"]
    assert "cite it by the number given here" in model.seen[0]["content"]
    assert "(Sghaier, 2022, p. 6)" in model.seen[-2]["content"]
    check = events[-1]
    assert check["cited"] == [1] and check["removed"] == []


def test_a_follow_up_of_a_literature_question_is_searched_again():
    model = Scripted("In Tunisia, rainfed groves lost NDVI [3].")
    asked = []
    list(
        answer(
            model,
            [
                {
                    "role": "user",
                    "content": "What do studies say about drought and olive NDVI in Spain?",
                },
                ANSWER,
                {"role": "user", "content": "And in Tunisia?"},
            ],
            search=lambda q: asked.append(q) or [],
        )
    )
    # searched by code, before the model could answer from the earlier papers
    assert asked == ["Tunisia drought olive NDVI"]
    assert model.calls == 1


def test_a_question_in_french_is_answered_in_french():
    model = Scripted("Bonjour.")
    list(answer(model, [{"role": "user", "content": "Bonjour, qu'est-ce que tu peux faire ?"}]))
    assert model.seen[-1]["content"].endswith("(Réponds en français.)")
