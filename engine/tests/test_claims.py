"""A claim from a paper, read by code and tested on the researcher's data (#171).

The verdicts are checked on the reference orchard (Jendouba, from the 2026 paper), replayed
from recorded Earth Engine answers, so they do not depend on the network.
"""

import sys
from pathlib import Path

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
