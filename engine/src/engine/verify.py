"""Checking a claim against a passage with a small model trained for that one task.

The support check (support.py) asks the chat model that wrote the answer whether a passage
supports a sentence of it: the answer is graded by its own author, in one word. A verifier is a
separate model, a few hundred million parameters, trained only to read a passage and a claim
and give the probability that the passage supports the claim. It runs on the CPU in a fraction
of a second, and it is the same every time.

Two kinds are offered, so they can be compared on the same claims (evaluation/verifiers.py):

- nli: a model trained on natural-language inference, the task of telling whether a text
  entails, contradicts or is neutral to a statement; the probability of "entailment" is used
- minicheck: models trained to check the sentences of language-model answers against their
  sources (Tang, Laban and Durrett, 2024); the probability of "supported" is used

Both need the optional dependencies: uv sync --extra verify. The weights are downloaded from
Hugging Face the first time a verifier is used.

To fit the support check, the probability is read as one of its three answers: yes at
SUPPORTED or above, partly at PARTLY or above, no below. The thresholds are calibrated on
statements labelled by people (evaluation/labels.py), not chosen by hand.
"""

import logging
from collections.abc import Callable
from functools import cache

log = logging.getLogger("magonia")

# name → Hugging Face model and how its output is read
VERIFIERS = {
    "nli": ("cross-encoder/nli-deberta-v3-base", "nli"),
    "minicheck-roberta": ("lytang/MiniCheck-RoBERTa-Large", "minicheck"),
    "minicheck-deberta": ("lytang/MiniCheck-DeBERTa-v3-Large", "minicheck"),
}
SUPPORTED = 0.5
PARTLY = 0.2
MAX_TOKENS = 512  # a passage of ~200 words and a sentence fit with room to spare
BATCH = 8


def verdict(probability: float) -> str:
    """The support check's answer for a probability of support."""
    if probability >= SUPPORTED:
        return "yes"
    return "partly" if probability >= PARTLY else "no"


class Verifier:
    """One verifier, loaded once and kept: loading takes seconds, a check milliseconds."""

    def __init__(self, name: str):
        import torch
        from transformers import AutoModelForSequenceClassification, AutoTokenizer

        model_id, self.kind = VERIFIERS[name]
        self.name = name
        self.torch = torch
        self.tokenizer = AutoTokenizer.from_pretrained(model_id)
        self.model = AutoModelForSequenceClassification.from_pretrained(model_id)
        self.model.eval()
        if self.kind == "nli":
            labels = {v.lower(): int(k) for k, v in self.model.config.id2label.items()}
            self.supports = labels["entailment"]
        else:
            self.supports = 1  # MiniCheck: 0 unsupported, 1 supported

    def inputs(self, pairs: list[tuple[str, str]]):
        passages = [p for p, _ in pairs]
        claims = [c for _, c in pairs]
        if self.kind == "nli":
            # a text pair: the passage is the premise, the claim the hypothesis
            return self.tokenizer(
                passages,
                claims,
                truncation="only_first",
                max_length=MAX_TOKENS,
                padding=True,
                return_tensors="pt",
            )
        # MiniCheck reads one text: the passage, the end-of-text token, the claim
        joined = [p + self.tokenizer.eos_token + c for p, c in pairs]
        return self.tokenizer(
            joined, truncation=True, max_length=MAX_TOKENS, padding=True, return_tensors="pt"
        )

    def support(self, pairs: list[tuple[str, str]]) -> list[float]:
        """The probability that each passage supports its claim; pairs are (passage, claim)."""
        out: list[float] = []
        with self.torch.no_grad():
            for i in range(0, len(pairs), BATCH):
                logits = self.model(**self.inputs(pairs[i : i + BATCH])).logits
                probs = self.torch.softmax(logits, dim=-1)[:, self.supports]
                out += [float(p) for p in probs]
        return out

    def judge(self, claim: str, passage: str) -> str:
        """The support check's judge: yes, partly or no."""
        return verdict(self.support([(passage, claim)])[0])


@cache
def load(name: str) -> Verifier:
    return Verifier(name)


def judge_for(name: str | None) -> Callable[[str, str], str] | None:
    """The judge a setting names, or None to keep asking the chat model."""
    if not name or name == "model":
        return None
    if name not in VERIFIERS:
        raise ValueError(f"unknown verifier {name!r}; choose from {', '.join(VERIFIERS)}")
    try:
        return load(name).judge
    except ImportError:  # the optional dependencies are not installed: keep the chat model
        log.warning("verifier %s needs `uv sync --extra verify`; the chat model judges", name)
        return None
