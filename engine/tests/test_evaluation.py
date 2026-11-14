"""The evaluation's own scoring, which every number of the comparison rests on."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "evaluation"))

import score
from cases import CASES, gold, jendouba_view
from score import (
    CONSENSUS,
    DECLINES,
    DENIES,
    chosen_judge,
    french,
    mentions,
    sentences,
    titles,
    value_given,
)


def test_the_scorer_names_who_judged_support_and_falls_back_to_the_chat_model(monkeypatch):
    def lean(messages, tools=None):
        yield "yes"

    _, who = chosen_judge("model", lean)
    assert who == "model"
    # a verifier that is not installed must not be reported as the judge
    monkeypatch.setattr(score, "judge_for", lambda name: None)
    _, who = chosen_judge("minicheck-roberta", lean)
    assert who == "model"
    monkeypatch.setattr(score, "judge_for", lambda name: (lambda claim, passage: "no"))
    judge, who = chosen_judge("minicheck-roberta", lean)
    assert who == "minicheck-roberta" and judge("a", "b") == "no"


def test_the_expected_answers_match_the_data():
    gold(jendouba_view())  # stops the run when they differ


def test_case_ids_are_unique():
    assert len({c.id for c in CASES}) == len(CASES)


def test_references_are_found_in_every_form():
    text = (
        "Smith et al. (2019) found it, as did (Ben Ali, 2020) and Gonzalez and Lopez (2018).\n"
        "Others agree (Bounouh et al., 2021; Rossi, 2017). Garcia et al., 2015 disagreed.\n"
        "1. Jones, K., & Brown, T. (2014). Olive NDVI. Remote Sensing.\n"
        "In (2016) the drought came."
    )
    assert mentions(text) == [
        ("Smith", 2019),
        ("Gonzalez", 2018),
        ("Bounouh", 2021),
        ("Garcia", 2015),
        ("Jones", 2014),
    ]


def test_quoted_titles_are_found_but_not_bold_headings():
    text = 'See "Drought effects on olive canopy greenness in Spain".\n**Limited Vegetation Adjustment Factor**'
    assert titles(text) == ["Drought effects on olive canopy greenness in Spain"]


def test_values_are_matched_at_their_decimals():
    assert value_given("peaks at 0.7 in March", 0.70, 2)
    assert value_given("it was −2.61 in September", -2.61, 2)
    assert not value_given("in 2012 it rose", 0.70, 2)
    assert not value_given("about 0.72", 0.70, 2)


def test_sentences_leave_out_headings_and_citations():
    text = (
        "### Drought effects\nNDVI fell by 18% in 2016 [1, p. 3]. It recovered soon after drought."
    )
    assert sentences(text) == ["NDVI fell by 18% in 2016.", "It recovered soon after drought."]


def test_refusals_and_denials_are_recognised():
    assert DENIES.search("I could not find a paper by Khayati from 2019.")
    assert DENIES.search("There is no such study in the papers found.")
    assert DENIES.search("None of the papers found directly address SAVI in Tunisia.")
    assert DENIES.search("The search results do not include any papers by Smith and Jones.")
    assert not DENIES.search("Khayati (2019) found that NDVI fell.")
    assert DECLINES.search("I'm sorry, but I can only help with remote sensing.")
    assert not DECLINES.search("Here is a poem about cats: soft paws...")


def test_counting_studies_is_caught():
    assert CONSENSUS.search("Most studies found a strong link.")
    assert CONSENSUS.search("Four of the six studies report a lag.")
    assert not CONSENSUS.search("In Spain, [1] found a lag of two months.")


def test_french_is_recognised():
    assert french("Le NDVI des oliviers est plus bas pendant la sécheresse dans le sud.")
    assert not french("NDVI of olive trees is lower during drought in the south.")
