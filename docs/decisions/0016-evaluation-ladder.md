# 0016. Evaluate against a ladder of systems with a shared evidence pool

Status: accepted

## Context
"You just wrapped an open model" is the obvious objection. Answering it needs the
contribution of each layer, not one score.

## Decision
`engine/evaluation/` asks the same cases to four systems on the same model: bare, prompted
(Mago's rules and the facts pasted in), the pipeline on abstracts, and the full pipeline.
Every statement is judged against the pool of everything any system was given for that
question; numbers are checked against values recomputed independently; searches of an
earlier run can be replayed so a before/after compares answers on the same papers.

## Consequences
Each difference between rungs is a measured contribution. The judge is the same model as the
generator and the cases were written by the developer: both are stated limits, to be met
with hand-labelled agreement (κ) and an independent case set.
