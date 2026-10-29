import pytest

from engine.proposals import ProposalError, describe, proposal

AREAS = ["Orchard", "Sfax"]


def test_a_request_becomes_a_checked_proposal():
    p = proposal(
        {
            "kind": "trend",
            "variable": "NDVI",
            "start": "2010",
            "end": "2020",
            "why": "Is it greening?",
        },
        AREAS,
    )
    assert p == {
        "kind": "trend",
        "label": "Long-term trend",
        "why": "Is it greening?",
        "variable": "ndvi",
        "period": {"start": "2010-01", "end": "2020-12"},
    }
    assert describe(p) == "Long-term trend: NDVI, period 2010-01 to 2020-12"


def test_an_experiment_gets_its_area_models_and_defaults():
    p = proposal(
        {"kind": "experiment", "area": "orchard", "models": ["random forest", "Ridge"], "why": "x"},
        AREAS,
    )
    assert p["area"] == "Orchard" and p["models"] == ["Ridge", "RandomForest"]
    assert p["drivers"] == ["lst", "spei"] and p["test_years"] == 3
    assert describe(p) == "Forecast experiment: NDVI with LST, SPEI, Orchard"


@pytest.mark.parametrize(
    ("arguments", "message"),
    [
        ({"kind": "clustering"}, "kind must be one of"),
        ({"kind": "trend", "variable": "rain"}, "ndvi, lst or spei"),
        ({"kind": "lags", "area": "Tunis"}, "no area is called 'Tunis'"),
        ({"kind": "trend", "start": "last year"}, "YYYY or YYYY-MM"),
        ({"kind": "experiment", "models": ["LSTM"]}, "Ridge, Random Forest or XGBoost"),
    ],
)
def test_proposals_that_do_not_fit_are_refused_with_a_reason(arguments, message):
    with pytest.raises(ProposalError, match=message):
        proposal({"why": "", **arguments}, AREAS)
