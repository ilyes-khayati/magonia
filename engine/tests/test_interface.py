"""The interface Magon is told about, and the check of the pages and buttons it names."""

import re
from pathlib import Path

from engine.assistant import APP, Scripted, answer
from engine.interface import ANALYSES, check_app


def names(text):
    return [(m.text, m.kind, m.status) for m in check_app(text)]


def test_made_up_buttons_are_flagged():
    # what Magon once wrote
    said = 'Click the "Seasonal Plot" button, then the **Anomaly Detection** button.'
    assert names(said) == [
        ("Seasonal Plot", "button", "unknown"),
        ("Anomaly Detection", "button", "unknown"),
    ]
    assert names('Use the "Interpolation Quality" tool.') == [
        ("Interpolation Quality", "tool", "unknown")
    ]


def test_real_pages_analyses_and_controls_pass():
    said = 'Go to the Analyses page, press "Add analysis" and choose **Season dates** analysis.'
    assert {s for _, _, s in names(said)} == {"known"}
    assert names('Open the "NDVI chart" card.') == [("NDVI chart", "card", "known")]
    assert names("The trend shows a decline over the period.") == []


def test_the_analyses_are_the_interfaces_own():
    web = (Path(__file__).parents[2] / "web/src/analyses.ts").read_text()
    assert set(re.findall(r'label: "([^"]+)"', web)) == set(ANALYSES)
    assert all(a in APP for a in ANALYSES)


def test_the_answer_reports_the_names_it_used():
    model = Scripted('Click the "Seasonal Plot" button.')
    events = list(answer(model, [{"role": "user", "content": "How do I see the season?"}]))
    assert events[-1]["app"][0]["status"] == "unknown"
