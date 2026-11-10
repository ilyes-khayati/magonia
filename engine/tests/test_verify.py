"""Verifiers: how their probability becomes the support check's answer, and how one is chosen."""

import pytest

from engine import verify


def test_a_probability_becomes_yes_partly_or_no():
    assert verify.verdict(0.9) == "yes"
    assert verify.verdict(verify.SUPPORTED) == "yes"
    assert verify.verdict(0.3) == "partly"
    assert verify.verdict(0.05) == "no"


def test_the_chat_model_judges_unless_a_verifier_is_chosen():
    assert verify.judge_for(None) is None
    assert verify.judge_for("model") is None
    with pytest.raises(ValueError, match="unknown verifier"):
        verify.judge_for("oracle")


def test_without_the_optional_libraries_the_chat_model_keeps_judging(monkeypatch):
    def missing(name):
        raise ImportError("No module named 'transformers'")

    monkeypatch.setattr(verify, "load", missing)
    assert verify.judge_for("nli") is None
