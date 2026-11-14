"""Verifiers: how their probability becomes the support check's answer, and how one is chosen."""

import builtins

import pytest

from engine import verify


def test_a_probability_becomes_yes_partly_or_no_at_the_verifiers_own_thresholds():
    spec = verify.VERIFIERS["minicheck-roberta"]
    assert verify.verdict(0.9) == "yes"
    assert verify.verdict(spec.supported) == "yes"
    assert verify.verdict(0.1) == "partly"
    assert verify.verdict(spec.withdraw) == "partly"
    assert verify.verdict(0.01) == "no"


def test_each_verifier_is_read_at_its_own_measured_thresholds():
    # 0.15 supports for MiniCheck-DeBERTa (0.12) but not yet for RoBERTa (0.18)
    assert verify.verdict(0.15, "minicheck-deberta") == "yes"
    assert verify.verdict(0.15, "minicheck-roberta") == "partly"
    # the NLI model's withdraw threshold is 0: it never says no
    assert verify.verdict(0.0, "nli") == "partly"
    for spec in verify.VERIFIERS.values():
        assert 0 <= spec.withdraw < spec.supported <= 1


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


def test_installed_says_whether_a_named_verifier_can_run_here(monkeypatch):
    assert verify.installed(None) and verify.installed("model")
    assert not verify.installed("oracle")
    real_import = builtins.__import__

    def without_torch(name, *args, **kwargs):
        if name == "torch":
            raise ImportError("No module named 'torch'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", without_torch)
    assert not verify.installed("minicheck-roberta")
    assert verify.installed("model")
