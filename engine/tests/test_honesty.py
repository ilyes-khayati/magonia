import pytest

"""Failures found by a researcher testing Magon on 14 November 2026, each kept as a test.

The texts are Magon's own answers from that session, cut to what each test needs.
"""

from pdf import make_pdf
from test_agent import orchard_view
from test_uploads import FIELD

from engine import honesty
from engine.assistant import (
    Scripted,
    ToolCall,
    answer,
    asked_readings,
    english_keywords,
    proposal_in_words,
    written_calls,
)
from engine.library import Library, Uploads
from engine.literature import Paper

SGHAIER = Paper(
    id="W1",
    title="Drought and olive NDVI",
    authors=["Ali Sghaier"],
    year=2022,
    venue="Journal",
    doi=None,
    abstract="An abstract.",
    open_access_url=None,
    cited_by=10,
    countries=["TN"],
)

# Test 16: a paper that does not exist, summarised from memory without a search
BEN_SALAH = (
    "The study by Ben Salah et al. (2019) focuses on the impact of drought on olive trees in "
    "Kairouan, Tunisia, using remote sensing data. Here is a summary of their key findings:\n\n"
    "- **Study Area and Data**: The research covers the Kairouan governorate in Tunisia, using "
    "satellite data from Sentinel-2 and climate data from SPEI.\n\n"
    "- Rainfed groves lost NDVI within one season of drought [1]."
)
# Test 17: says it searched when no search ran
HAILSTORMS = (
    'A search of the literature using the keywords "2024 hailstorms olive NDVI Béja" did not '
    "yield any relevant papers. Therefore, no published studies have been found that address "
    "the effect of 2024 hailstorms on olive NDVI in Béja."
)
# Test 8: the definition of SPEI turned upside down
SPEI_SIGN = (
    "The researcher's data show that higher SPEI values generally correspond to drier "
    "conditions. The annual means of NDVI are lowest in years with lower SPEI values."
)


def test_a_paper_that_was_not_found_is_withdrawn_with_what_describes_it():
    gone = honesty.withdrawn(BEN_SALAH, [SGHAIER], searched=True)
    claims = [s.claim for s in gone]
    assert claims[0].startswith("The study by Ben Salah et al. (2019)")
    assert any("Kairouan governorate" in c for c in claims)
    # the sentence citing a paper that was found stays, and stops the withdrawal
    assert not any("Rainfed groves" in c for c in claims)
    assert "Salah (2019) was found" in gone[0].evidence or "Salah" in gone[0].evidence


def test_saying_a_paper_was_not_found_is_kept():
    text = "I could not find Ben Salah et al. (2019) among the papers the search returned."
    assert honesty.withdrawn(text, [SGHAIER], searched=True) == []


def test_a_paper_that_was_found_is_not_withdrawn_in_any_form():
    for text in (
        "Sghaier et al. (2022) found that groves lost NDVI.",
        "Groves lost NDVI (Sghaier et al., 2022).",
        "Groves lost NDVI (Sghaier, 2022).",
    ):
        assert honesty.withdrawn(text, [SGHAIER], searched=True) == [], text


def test_places_and_dates_are_not_references():
    text = (
        "In 2023, NDVI in Jendouba fell. Hailstorms hit Béja, 2024, and Tunisia 2022 was dry. "
        "From March 2020 to July 2021 SPEI stayed low."
    )
    assert honesty.mentions(text) == []


def test_a_search_that_did_not_happen_is_withdrawn_one_that_did_is_kept():
    gone = honesty.withdrawn(HAILSTORMS, [], searched=False)
    assert len(gone) == 1 and gone[0].claim.startswith("A search of the literature")
    assert "No literature search" in gone[0].evidence
    assert honesty.withdrawn(HAILSTORMS, [], searched=True) == []


def test_spei_and_lst_turned_upside_down_are_withdrawn():
    gone = honesty.withdrawn(SPEI_SIGN, [], searched=False)
    assert [s.claim for s in gone] == [
        (
            "The researcher's data show that higher SPEI values generally correspond to drier "
            "conditions."
        )
    ]
    assert "wetter" in gone[0].evidence
    for right in (
        "Higher SPEI means wetter conditions.",
        "Lower SPEI values mark drought.",
        "Higher LST means a hotter, drier surface.",
    ):
        assert honesty.withdrawn(right, [], searched=False) == [], right
    assert honesty.withdrawn("Higher LST values make orchards cooler.", [], searched=False)


def test_the_answer_withdraws_a_paper_from_memory_and_says_why():
    # it names a paper without searching; code searches, it answers again the same way
    model = Scripted(BEN_SALAH.split("\n\n")[0], BEN_SALAH.split("\n\n")[0])
    events = list(
        answer(
            model,
            [{"role": "user", "content": "Summarise the findings of Ben Salah et al. (2019)."}],
            search=lambda query: [],
        )
    )
    assert [e["query"] for e in events if e["type"] == "search"]  # searched by code
    check = events[-1]
    assert "Ben Salah" not in check["text"]
    assert "contradicted what Magon can check" in check["text"]
    assert check["withdrawn"] and check["withdrawn"][0]["source"] == "Magonia's check"


def test_ok_i_added_it_is_about_the_question_before():
    # test 9: routed as small talk, it got no facts and invented "lag 12 stands out"
    model = Scripted("Fine.")
    events = list(
        answer(
            model,
            [
                {"role": "user", "content": "Which lag of SPEI stands out for NDVI in my orchard?"},
                {"role": "assistant", "content": "Add a lags analysis to see it."},
                {"role": "user", "content": "ok I added it"},
            ],
            view=orchard_view(),
        )
    )
    assert events[0]["kind"] == "data"
    assert "What is open in Magonia" in model.seen[-1]["content"]
    # a greeting stays small talk
    events = list(
        answer(
            Scripted("Hello."),
            [
                {"role": "user", "content": "Which lag of SPEI stands out?"},
                {"role": "assistant", "content": "Lag 1."},
                {"role": "user", "content": "thanks!"},
            ],
            view=orchard_view(),
        )
    )
    assert events[0]["kind"] == "chat"


def test_the_values_of_a_year_are_read_by_code_before_the_model_answers():
    # test 6: it skipped the tool and wrote twelve months of its own
    view = orchard_view()
    assert asked_readings("What were the monthly NDVI values in 2023?", view) == [
        (view.series[0].area, "ndvi", 2023)
    ]
    assert asked_readings("Which year had the lowest NDVI?", view) == []
    model = Scripted("Here they are.")
    events = list(
        answer(
            model,
            [{"role": "user", "content": "What were the monthly NDVI values in 2023?"}],
            view=view,
        )
    )
    assert any(e["type"] == "read" and e["year"] == 2023 for e in events)
    assert "Read from the researcher's series" in model.seen[-1]["content"]


def test_a_proposal_written_in_words_becomes_a_button():
    # test 10: "Proposed action: Analyses, Add analysis, Decomposition." and no button
    said = (
        'To decompose the NDVI, we can add a "Decomposition" analysis.\n\n'
        "Proposed action: Analyses, Add analysis, Decomposition.\n\n"
        "This analysis will separate the NDVI into its trend and seasonal components."
    )
    question = "Can you decompose my NDVI into trend and seasonal parts?"
    found = proposal_in_words(question, said, ["Orchard"])
    assert found["kind"] == "decomposition" and found["variable"] == "ndvi"
    found = proposal_in_words("Let's look at the trend of LST.", "", ["Orchard"])
    assert found["kind"] == "trend" and found["variable"] == "lst"
    events = list(
        answer(Scripted(said), [{"role": "user", "content": question}], view=orchard_view())
    )
    proposals = [e for e in events if e["type"] == "proposal"]
    assert len(proposals) == 1 and proposals[0]["proposal"]["kind"] == "decomposition"
    assert "Proposed action" not in events[-1]["text"]


def test_a_french_question_is_searched_in_english():
    # test 4: "sécheresse NDVI oliviers" found nothing on OpenAlex
    class Translates(Scripted):
        def english_keywords(self, question):
            return "drought NDVI olive"

    asked = []
    model = Translates(ToolCall("search_papers", {"query": "sécheresse NDVI oliviers"}), "Réponse.")
    list(
        answer(
            model,
            [{"role": "user", "content": "Quelles études parlent de la sécheresse et du NDVI ?"}],
            search=lambda query: asked.append(query) or [],
        )
    )
    assert asked == ["drought NDVI olive"]
    # a model that cannot translate keeps its own query
    assert english_keywords(Scripted(), "Quelles études ?", "sécheresse") == "sécheresse"


# The second round of a researcher's tests, 14 November: what the first fixes got wrong

CORRECT = [
    # withdrawn as wrong by the first SPEI check, though right: both directions are given
    (
        "Positive SPEI values indicate wetter conditions, while negative values indicate drier "
        "conditions."
    ),
    "No, higher SPEI indicates wetter conditions.",
    "Higher SPEI means wetter; lower SPEI means drier.",
    "Lower SPEI values mark drought, and higher values wetter months.",
    "Higher LST means a hotter, drier surface.",
    "SPEI below zero is drier than usual, above zero wetter.",
]
WRONG = [
    (
        "The researcher's data show that higher SPEI values generally correspond to drier "
        "conditions."
    ),
    "Higher LST values make orchards cooler.",
    "Lower SPEI values indicate wetter months.",
    "A rising SPEI points to drought.",
]


def test_the_sign_check_raises_no_false_alarm_on_correct_definitions():
    assert [s for s in CORRECT if honesty.upside_down(s)] == []
    assert [s for s in WRONG if not honesty.upside_down(s)] == []


def test_a_search_written_as_text_is_made_and_its_claim_withdrawn():
    said = '- Search_papers("olive NDVI hailstorms Béja 2024") yielded no relevant results.'
    calls, rest = written_calls(said)
    assert [(c.name, c.arguments) for c in calls] == [
        ("search_papers", {"query": "olive NDVI hailstorms Béja 2024"})
    ]
    assert "Search_papers" not in rest
    # if it stays in an answer with no search made, the sentence is withdrawn
    assert honesty.withdrawn(said, [], searched=False)


def test_ok_before_a_new_question_routes_the_question_itself():
    # inheriting sent "ok what lag is important for ndvi here?" to the literature
    model = Scripted("Fine.")
    events = list(
        answer(
            model,
            [
                {"role": "user", "content": "What have published studies found about hail?"},
                {"role": "assistant", "content": "None were found."},
                {"role": "user", "content": "ok what lag is important for ndvi here?"},
            ],
            view=orchard_view(),
            search=lambda query: [],
        )
    )
    assert events[0]["kind"] != "research"
    assert "What is open in Magonia" in model.seen[-1]["content"]


def test_a_library_file_does_not_stop_the_search(tmp_path):
    # with the researcher's file given as relevant, the model skipped the search and gave
    # the file invented findings of a paper that does not exist
    shelf = Library(tmp_path / "library.db")
    Uploads(shelf).add("survey.pdf", make_pdf([FIELD]))
    asked = []
    events = list(
        answer(
            Scripted("Ben Salah et al. (2019) found that olive NDVI fell [1].", "Nothing found."),
            [{"role": "user", "content": "What did studies find on olive NDVI loss in Jendouba?"}],
            library=shelf,
            search=lambda query: asked.append(query) or [],
        )
    )
    assert asked, "the search must run"
    assert "Ben Salah" not in events[-1]["text"]


# Research said to have found something, with no paper named and none found: the sentence
# that escaped the author–year check (15 Nov)
FROM_MEMORY = [
    "Studies have shown that olive NDVI responds to drought within two months.",
    "A 2019 study in Kairouan found that olive groves recover quickly.",
    "According to the literature, olive leaves live about two years.",
    "Research indicates that understory grass dominates the signal.",
    "It has been reported that olive trees shed leaves in summer.",
    "Several studies in Spain have consistently reported a lag of one month.",
]
NOT_FROM_MEMORY = [
    "Positive SPEI values indicate wetter conditions.",
    "No studies have shown a link between hail and NDVI in Béja.",
    "NDVI peaks in March (0.61) (NDVI chart).",
    "Researchers often use SPEI-3 for agricultural drought.",
    "My own reading is that the March peak comes from grass under the trees.",
]


def test_research_cited_from_memory_is_withdrawn_when_no_paper_was_read():
    for sentence in FROM_MEMORY:
        assert honesty.withdrawn(sentence, [], searched=False), sentence


def test_the_same_sentence_stands_for_the_other_checks_when_papers_were_found():
    # with papers found, a sentence citing none is the uncited check's to judge
    for sentence in FROM_MEMORY:
        assert not honesty.withdrawn(sentence, [SGHAIER], searched=True), sentence


def test_no_false_alarm_on_sentences_that_do_not_cite_research():
    for sentence in NOT_FROM_MEMORY:
        assert not honesty.withdrawn(sentence, [], searched=False), sentence


# review of 18 Nov: correct statements about the researcher's data were withdrawn as if they
# were claims about a literature search or about unnamed research
@pytest.mark.parametrize(
    "sentence",
    [
        "The Mann-Kendall test found no significant trend in your NDVI (Trend card).",
        "The lag explorer did not find a lag beyond chance.",
        "A correlation analysis shows that NDVI rises with SPEI (Correlation card).",
        "It is shown in the NDVI chart that the peak comes in March.",
    ],
)
def test_statements_about_the_researchers_own_data_are_not_withdrawn(sentence):
    assert honesty.withdrawn(sentence, [], searched=False) == []


def test_a_cited_paper_named_with_its_accent_or_print_year_is_not_taken_for_an_invention():
    from types import SimpleNamespace

    papers = [SimpleNamespace(authors=["José Martínez"], year=2019)]
    assert (
        honesty.withdrawn("Martinez et al. (2019) found NDVI fell [1].", papers, searched=True)
        == []
    )
    assert honesty.withdrawn("Martinez et al. (2020) found NDVI fell.", papers, searched=True) == []
    assert honesty.withdrawn("Smith et al. (2018) found NDVI fell.", papers, searched=True) != []


def test_places_and_relief_are_not_mistaken_review_of_18_nov():
    # a governorate and a year is not a reference; a relief verb is not an inverted definition
    assert honesty.mentions("Hail in Jendouba (2019) lowered NDVI.") == []
    assert honesty.upside_down("Higher SPEI values reduce drought stress on the trees.") == ""
    assert honesty.upside_down("Higher SPEI values mean drier conditions.") != ""
