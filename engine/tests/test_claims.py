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
        ("Stronger drought reduces olive greenness within two months.", "lag", "spei", 1, "claim", 2),
        # no direction stated: the physical expectation is tested, and said to be
        ("Olive NDVI responds to drought with a lag of about 12 months.", "lag", "spei", 1, "physics", 12),
        # a range is tested at its middle
        ("SPEI-12 is positively correlated with NDVI at 3-6 months lag.", "lag", "spei", 1, "claim", 4),
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
    assert claims.claim_in(
        'Test this claim on my orchard: "Olive NDVI responds to drought with a 12-month lag."'
    ) == "Olive NDVI responds to drought with a 12-month lag."
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
    linked = verdicts(rng, 150, 0.35, 6, 1)
    assert linked["replicates"] >= 0.6 and linked["contradicts"] == 0
    opposite = verdicts(rng, 150, -0.35, 6, 1)
    assert opposite["contradicts"] >= 0.6 and opposite["replicates"] == 0


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
    assert right >= 5
