# 0006. Numbers are checked by code, not trusted from the model

Status: accepted

## Context
Since version 1.5 the assistant discusses the researcher's own data. It is given
facts computed by code for each chart and analysis on screen (`engine.facts`),
and can read a series more closely through a tool. In a live test with the
local 7B model it still wrote twelve monthly NDVI values for a year it had never
read: plausible, precise and invented. An invented number about a researcher's
own area is as harmful as an invented reference, and harder to spot.

## Decision
After an answer is written, `engine.numbers.check_numbers` finds every number in
it and looks for it in what the model was given for that answer: the question,
the facts about the open workspace, the readings it took, and the titles and
abstracts of the papers it found. A number matches when it is the same, or the
given number rounded to as many decimals as were written; more precision than
given does not match. A number found only with the opposite sign is reported
apart, since a flipped sign reverses a conclusion. Dates, citation numbers and
list numbering are not measurements and are skipped. The check runs whenever the
answer had a workspace or papers to rely on.

The interface underlines verified numbers and names their source on hover
("NDVI chart", "reading Corn NDVI 2022"), highlights the others, and says under
the answer how many numbers were confirmed. The evaluation reports the share of
numbers in data answers found in what the model was given.

## Consequences
An invented number cannot reach the researcher looking like a checked one,
whatever the model, and the guarantee is tested without a model
(`test_numbers.py`, `test_agent.py`). The check proves that a number was given,
not that the sentence around it uses it correctly: "r = 0.15, within chance"
passes even when 0.15 lies outside the chance band. Checking such claims needs
structured statements rather than free text, and is left for later. Numbers that
are general knowledge rather than data (NDVI ranges from -1 to 1) are flagged
too; the interface words this as "not found in what Magonia was given", not as
an error.
