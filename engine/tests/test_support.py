from engine.assistant import Scripted, ToolCall, answer
from engine.fulltext import Passage
from engine.library import Library
from engine.literature import Paper
from engine.support import check_support, faithfulness, judge_with, statements

PASSAGE = "Vineyards and olive groves respond to long SPEI timescales during summer months."
EVIDENCE = {1: [("[1, p. 18]", PASSAGE)], 2: [("[2] abstract", "Wheat yields in Canada.")]}


def test_only_sentences_that_cite_are_statements():
    text = "Hello there. Olive groves respond to long timescales [1]. **Wheat** grows [2, p. 3]."
    found = statements(text)
    assert [(claim, cites) for _, _, claim, cites in found] == [
        ("Olive groves respond to long timescales.", [1]),
    ]  # "Wheat grows." has too few words to be a claim
    start, end, _, _ = found[0]
    assert text[start:end] == "Olive groves respond to long timescales [1]."


def test_without_a_judge_code_only_rules_out_what_the_papers_do_not_discuss():
    text = (
        "Olive groves respond to long SPEI timescales in summer [1]. "
        "Barley prices rose sharply in Morocco last year [1]."
    )
    found = check_support(text, EVIDENCE)
    assert [s.status for s in found] == ["unclear", "unsupported"]
    assert found[0].source == "[1, p. 18]" and found[0].evidence == PASSAGE
    assert faithfulness(found) == 0.0


def test_the_judge_decides_claims_on_the_subject():
    asked = []

    def judge(claim, passage):
        asked.append(claim)
        return "no" if "winter" in claim else "yes"

    text = (
        "Olive groves respond to long SPEI timescales in summer [1]. "
        "Olive groves respond to short SPEI timescales in winter [1]."
    )
    found = check_support(text, EVIDENCE, judge=judge)
    assert [s.status for s in found] == ["supported", "unsupported"]
    assert all(s.judged for s in found) and len(asked) == 2
    assert faithfulness(found) == 0.5


def test_a_claim_is_compared_only_with_the_papers_it_cites():
    found = check_support("Olive groves respond to long SPEI timescales [2].", EVIDENCE)
    assert found[0].status == "unsupported" and found[0].source == "[2] abstract"


def test_the_judge_reads_the_first_word_and_survives_a_dead_model():
    assert judge_with(lambda messages, tools: iter(["Yes, ", "it does."]))("a", "b") == "yes"
    assert judge_with(lambda messages, tools: iter(["Maybe"]))("a", "b") == "no"

    def dead(messages, tools):
        raise OSError("no route to host")
        yield

    assert judge_with(dead)("a", "b") == "partly"


def test_the_answer_reports_support_and_faithfulness(tmp_path):
    paper = Paper(
        "W1",
        "Drought in Spain",
        ["A. Vicente"],
        2019,
        None,
        None,
        "Abstract.",
        None,
        0,
        [],
        pdf_url="https://example.org/1.pdf",
    )
    shelf = Library(tmp_path / "library.db", reader=lambda url: [Passage(18, PASSAGE * 3)])
    model = Scripted(
        ToolCall("search_papers", {"query": "olive drought"}),
        "Olive groves respond to long SPEI timescales in summer [1, p. 18].",
    )
    events = list(
        answer(
            model,
            [{"role": "user", "content": "What do studies say about olive drought?"}],
            search=lambda query: [paper],
            library=shelf,
            judge=lambda claim, passage: "yes",
        )
    )
    kinds = [e["type"] for e in events if e["type"] != "text"]
    assert kinds[-2:] == ["verifying", "check"]
    check = events[-1]
    assert check["faithfulness"] == 1.0
    assert check["support"][0]["status"] == "supported"
    assert check["support"][0]["source"] == "[1, p. 18]"


def test_a_paragraph_that_starts_with_a_citation_carries_it():
    text = "[1] Smith et al. found olive NDVI falls in drought. The study also mapped irrigated groves near Jaén.\n\nOther text here without any citation."
    found = statements(text)
    assert [(claim, cites) for _, _, claim, cites in found] == [
        ("Smith et al. found olive NDVI falls in drought.", [1]),
        ("The study also mapped irrigated groves near Jaén.", [1]),
    ]


def test_a_second_passage_is_asked_when_the_closest_does_not_say_it():
    evidence = {
        1: [
            ("[1, p. 2]", "Olive groves respond to SPEI timescales in many regions of Spain."),
            ("[1, p. 9]", "Olive groves respond to long SPEI timescales during summer."),
        ]
    }

    def judge(claim, passage):
        return "yes" if "summer" in passage else "partly"

    found = check_support(
        "Olive groves respond to long SPEI timescales in summer [1].", evidence, judge=judge
    )
    assert found[0].status == "supported" and found[0].source == "[1, p. 9]"


def test_a_heading_passes_its_citation_to_the_points_under_it():
    text = (
        "**Impact of drought on olive NDVI** [1]\n"
        "- NDVI of rainfed olive groves fell during the 2012 drought.\n"
        "- Irrigated groves kept their NDVI through the summer.\n\n"
        "Further research is needed on this question."
    )
    assert [(claim, cites) for _, _, claim, cites in statements(text)] == [
        ("NDVI of rainfed olive groves fell during the 2012 drought.", [1]),
        ("Irrigated groves kept their NDVI through the summer.", [1]),
    ]


def test_a_reference_names_a_paper_and_is_not_a_claim():
    # the authors and year, and the title in italics, came back as "not supported"
    text = (
        "[1] Mahfoudhi et al., 1998. *Viruses and virus diseases of grapevine in Tunisia.* "
        "EPPO Bulletin. They found that most of the vines tested were infected.\n\n"
        "[2] Mahfoudhi and Dhouibi, 2009. *Survey of mealybugs in Tunisian vineyards.* "
        "African Entomology. Two species were found, with N. australe on old vines."
    )
    assert [claim for _, _, claim, _ in statements(text)] == [
        "They found that most of the vines tested were infected.",
        "Two species were found, with N. australe on old vines.",
    ]
