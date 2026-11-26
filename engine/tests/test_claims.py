"""A claim from a paper, read by code and tested on the researcher's data (#171).

The verdicts are checked on the reference orchard (Jendouba, from the 2026 paper), replayed
from recorded Earth Engine answers, so they do not depend on the network.
"""

import json
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "evaluation"))

from cases import jendouba_view

from engine import claims
from engine.assistant import Scripted, answer


@pytest.fixture(scope="module")
def orchard():
    return jendouba_view()


@pytest.mark.parametrize(
    ("text", "kind", "driver", "sign", "sign_from", "lag"),
    [
        # drought is low SPEI: "drought lowers NDVI" is NDVI rising with SPEI
        ("Drought lowers olive NDVI the following year.", "lag", "spei", 1, "claim", 12),
        # the way the driver moves is read apart from the verb
        ("Higher LST reduces NDVI one month later.", "lag", "lst", -1, "claim", 1),
        ("Less rain lowers NDVI three months later.", "lag", "rain", 1, "claim", 3),
        (
            "Stronger drought reduces olive greenness within two months.",
            "lag",
            "spei",
            1,
            "claim",
            2,
        ),
        # no direction stated: the physical expectation is tested, and said to be
        (
            "Olive NDVI responds to drought with a lag of about 12 months.",
            "lag",
            "spei",
            1,
            "physics",
            12,
        ),
        # a range is tested at its middle
        (
            "SPEI-12 is positively correlated with NDVI at 3-6 months lag.",
            "lag",
            "spei",
            1,
            "claim",
            4,
        ),
        ("Olive NDVI has declined since 2000.", "trend", None, -1, "claim", None),
    ],
)
def test_a_claim_is_read_into_what_it_asserts(text, kind, driver, sign, sign_from, lag):
    claim = claims.read(text)
    assert (claim.kind, claim.response, claim.driver, claim.sign, claim.sign_from, claim.lag) == (
        kind,
        "ndvi",
        driver,
        sign,
        sign_from,
        lag,
    )


def test_what_is_not_a_testable_claim_is_said_to_be():
    assert claims.read("Wheat prices rose sharply in Morocco.") is None
    assert claims.read("NDVI is a vegetation index.") is None  # no driver and no change


def test_the_claim_is_found_in_the_message():
    assert (
        claims.claim_in(
            'Test this claim on my orchard: "Olive NDVI responds to drought with a 12-month lag."'
        )
        == "Olive NDVI responds to drought with a 12-month lag."
    )
    assert claims.claim_in("Check this finding: higher LST reduces NDVI a month later") == (
        "higher LST reduces NDVI a month later"
    )
    assert claims.asks_to_test("Does this claim hold for my orchard?")
    assert claims.asks_to_test("Test this finding on my data: drought lowers NDVI")
    assert not claims.asks_to_test("What does drought do to olive NDVI?")


def test_a_claim_that_holds_replicates(orchard):
    # LST anomalies one month earlier: r = -0.41 against a bound of 0.22
    result = claims.test(claims.read("Higher LST reduces NDVI one month later."), orchard)
    assert result.verdict == "replicates" and result.details["lag"] == 1
    assert result.details["r"][0] < -result.details["bound"]


def test_a_claim_with_the_wrong_sign_is_contradicted(orchard):
    result = claims.test(claims.read("Higher LST raises NDVI one month later."), orchard)
    assert result.verdict == "contradicts"


def test_a_claim_that_finds_nothing_is_undecided_and_names_what_stands_out(orchard):
    # SPEI-3 at 12 months is within chance here; 1 month stands out
    result = claims.test(
        claims.read("Olive NDVI responds to drought with a lag of about 12 months."), orchard
    )
    assert result.verdict == "undecided"
    assert any("stand out is 1 month " in line for line in result.summary)
    assert any("one accumulation scale" in line for line in result.summary)


def test_a_trend_claim_is_tested_with_mann_kendall(orchard):
    result = claims.test(claims.read("Olive NDVI has declined since 2000."), orchard)
    assert result.verdict == "undecided" and result.details["p"] > 0.05


def test_a_claim_on_data_that_is_not_open_cannot_be_tested(orchard):
    result = claims.test(claims.read("Less rain lowers NDVI three months later."), orchard)
    assert result.verdict == "cannot test"
    assert "RAIN" in result.summary[0]


def test_magon_reports_the_verdict_code_reached(orchard):
    model = Scripted("It replicates on your orchard.")
    events = list(
        answer(
            model,
            [
                {
                    "role": "user",
                    "content": 'Test this claim on my orchard: "Higher LST reduces NDVI one '
                    'month later."',
                }
            ],
            view=orchard,
        )
    )
    assert events[0]["kind"] == "data"
    tested = next(e for e in events if e["type"] == "claim_test")["test"]
    assert tested["verdict"] == "replicates"
    assert tested["reading"] == "NDVI falls with LST 1 month earlier"
    assert "Verdict, decided by code: REPLICATES" in model.seen[-1]["content"]


def test_verdicts_on_orchards_with_a_known_truth():
    # the calibration of evaluation/claim_calibration.py, smaller: with no link the claim
    # almost never replicates, a clear link mostly does, and a sign is never mistaken
    sys.path.insert(0, str(Path(__file__).parent.parent / "evaluation"))
    from claim_calibration import verdicts

    rng = np.random.default_rng(0)
    none = verdicts(rng, 150, 0.0, 6, 1)
    assert none["replicates"] <= 0.05 and none["contradicts"] <= 0.05
    # since 18 Nov a claim must survive four implications (falsify.py), which costs power:
    # the plan (evaluation/falsification_plan.md) accepted that before the first run
    linked = verdicts(rng, 150, 0.35, 6, 1)
    assert linked["replicates"] >= 0.35 and linked["contradicts"] == 0
    opposite = verdicts(rng, 150, -0.35, 6, 1)
    assert opposite["contradicts"] >= 0.6 and opposite["replicates"] == 0


def test_a_driver_that_only_follows_vegetation_is_not_taken_for_a_cause():
    # feedback: this month's driver follows this month's vegetation, with no effect on it;
    # last month's driver then shares the vegetation's memory and seems to lead it. The
    # single correlation test confirmed such a link in 97.5% of 1,000 simulated records
    sys.path.insert(0, str(Path(__file__).parent.parent / "evaluation"))
    from falsification_calibration import as_series, record

    rng = np.random.default_rng(1)
    claim = claims.Claim("synthetic", "lag", "ndvi", "lst", -1, "claim", 1)
    held = 0
    for _ in range(100):
        veg, drv = record(rng, "feedback", {"c": 0.6})
        held += (
            claims.lag_test(claim, as_series(veg, "ndvi"), as_series(drv, "lst")).verdict
            == "replicates"
        )
    assert held <= 10


REAL = json.loads((Path(__file__).parent / "data" / "real_claims.json").read_text())


def reading(text):
    claim = claims.read(text)
    return None if claim is None else [claim.kind, claim.driver, claim.sign]


@pytest.mark.parametrize("item", REAL["development"], ids=lambda item: item["text"][:40])
def test_real_claims_from_papers_are_read_as_labelled_by_hand(item):
    if item["text"].startswith("In the case of the olive grove cover"):
        # a comparison between two vegetation covers: not a claim one series can test, and
        # not one patterns can tell from a claim; a known miss, shown to the researcher by
        # the reading that comes with the verdict
        pytest.xfail("comparisons between covers are read as claims")
    assert reading(item["text"]) in item["expected"]


def test_genuine_claims_held_out_are_read_right_and_the_rest_counted():
    # run once before the rain rule was generalised: 5 of 11 overall, 4 of 5 genuine claims.
    # A researcher picks the sentence to test, so genuine claims are what matters; sentences
    # that are not claims (histories, dataset lists) are mostly not refused, which is known
    genuine = [i for i in REAL["held_out"] if None not in i["expected"]]
    assert all(reading(i["text"]) in i["expected"] for i in genuine)
    right = sum(reading(i["text"]) in i["expected"] for i in REAL["held_out"])
    assert right >= 7  # 7 of 11 once the refusal rules were added (15 Nov)


def test_sentences_that_are_not_claims_are_refused():
    # held_out_2, measured once before the refusal rules (15 Nov): 6 of 20, 1 of 12
    # non-claims refused, and two stated positive correlations read as negative. The rules
    # were then written on it, so it is now a development set
    assert all(reading(i["text"]) in i["expected"] for i in REAL["held_out_2"])


def test_refusing_non_claims_holds_on_sentences_it_was_not_written_on():
    # held_out_3, labelled before the reader was run on it, run once (15 Nov): 16 of 18,
    # every genuine claim read right, 10 of 12 non-claims refused. The two missed: a
    # conditional ("the response varies with soil and vegetation type") and a contrast in
    # space ("maximised at the west side"), left as they are, so the number stays honest
    held = REAL["held_out_3"]
    genuine = [i for i in held if None not in i["expected"]]
    assert all(reading(i["text"]) in i["expected"] for i in genuine)
    assert sum(reading(i["text"]) in i["expected"] for i in held) >= 16


def test_magon_is_told_what_the_verdict_means():
    # left to explain REPLICATES, Magon wrote that the data showed "the opposite of the claim"
    result = claims.ClaimTest(claims.read("Higher LST reduces NDVI one month later."), "replicates")
    assert "which means the researcher's data show what the claim says" in claims.block(result)


def test_the_explanations_in_an_answer_are_tested_on_the_data(orchard):
    text = (
        "**What it could mean here**: a hotter surface may lower NDVI one month later [2]. "
        "Higher LST reduces NDVI one month later. Olive trees are evergreen. To test these "
        "possibilities, consider analyzing the correlation between SPEI and NDVI."
    )
    results = claims.tests_of(text, orchard)
    # the same claim twice is tested once; a sentence that is no claim is left out
    assert [r.claim.reading() for r in results] == ["NDVI falls with LST 1 month earlier"]
    assert results[0].verdict == "replicates"
    part = claims.tested_part(results)
    assert part.startswith("**Tested on your data**")
    assert "- NDVI falls with LST 1 month earlier: replicates." in part
    assert claims.tested_part([]) == ""


def test_magon_adds_the_tests_of_its_explanations(orchard):
    model = Scripted("**What it could mean here**: higher LST reduces NDVI one month later.")
    final = list(
        answer(
            model,
            [{"role": "user", "content": "Why does NDVI fall in summer here?"}],
            view=orchard,
            search=lambda q: [],
        )
    )[-1]
    assert "**Tested on your data**" in final["text"]
    assert final["tested"][0]["verdict"] == "replicates"


@pytest.mark.parametrize(
    "text, lag",
    [
        ("NDVI correlates positively with the 12-month SPEI.", None),
        ("NDVI responds to SPEI-12 with a lag of 2 months.", 2),
        ("Drought at the 6-month scale lowers NDVI.", None),
        ("Olive NDVI responds to drought with a lag of about 12 months.", 12),
    ],
)
def test_an_accumulation_scale_is_not_read_as_a_delay(text, lag):
    # review of 18 Nov: "the 12-month SPEI" was tested as a 12-month lag
    assert claims.read(text).lag == lag
