# 0019. A separate verifier checks support, at thresholds measured on expert labels

Status: accepted

## Context
The support check asked the chat model whether a passage supports a sentence it had itself
written: the answer graded by its author. The evaluation ladder (0016) named this as its
first threat to validity. A verifier is a small model trained only to read a passage and a
claim; three were compared on SciFact dev (340 claim–passage pairs labelled by experts). Their
probabilities are not calibrated: MiniCheck-RoBERTa separates supported from unsupported
best at 0.18, not 0.5, so a threshold assumed rather than measured would misread it.

## Decision
MiniCheck-RoBERTa checks support by default (AUC 0.89, κ 0.64 against the expert labels,
as good as the 7B chat model's 0.87 and 0.66, four times faster, and not the model that wrote
the answer). Each verifier carries two thresholds measured on SciFact: *supported*, the
threshold with the best balanced accuracy, and *withdraw*, the highest threshold that
withdraws at most 5% of the claims the experts called supported. At RoBERTa's withdraw
threshold (0.021), 49% of unsupported claims are withdrawn. Withdrawing a true statement
costs more than keeping a doubtful one marked unclear, which is why the second threshold is
set from the supported claims alone. The verifier runs inside the API (`uv sync --extra verify`
in `api/`); when it is not installed the chat model judges and Settings says so.

## Consequences
Support verdicts no longer come from the generator. The thresholds are chosen and measured on
the same claims, so the figures at them are optimistic, and SciFact passages are abstracts,
not Magon's 200-word passages: both are stated limits. The evaluation's own scorer must use
the same verifier, or the ladder's "supported" figure stays a self-judgement. The NLI model
is kept for comparison only: no threshold withdraws safely with it.
