# 0005. Citations are checked by code, not trusted from the model

Status: accepted

## Context
Language models invent references: plausible authors, years and titles that do
not exist. A research assistant that does this cannot be trusted, and a small
local model does it more often than a large one. Asking the model to behave is
not a guarantee.

## Decision
The model can only cite papers by number, and the numbers refer to the papers
that a search actually returned in this answer (OpenAlex, numbered in order
across searches). After the answer is written, `engine.citations.check` keeps
every number that points to a retrieved paper, removes every number that does
not, and reports what it removed. Author–year mentions that match no retrieved
paper are kept but flagged as unverified. The interface shows the checked
sources under the answer and states any removal.

## Consequences
An invented reference cannot reach the researcher as a citation, whatever the
model, and the guarantee is tested without a model (`test_citations.py`,
`test_agent.py`). The check proves that a cited paper was retrieved, not that it
supports the sentence; that needs reading the passage, which comes with full
text (1.4) and is measured in the evaluation (`engine/evaluation/`).
Numbered citations are less readable than author–year ones, so the interface
shows the author and year beside each number.
