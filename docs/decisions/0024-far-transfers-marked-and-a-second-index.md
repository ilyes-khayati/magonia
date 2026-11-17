# 0024. A far paper applied to the researcher's data is marked by code; Crossref backs up OpenAlex

Status: accepted

## Context

The controlled-evidence test of 17 November (ADR 0023) gave Magon papers from other settings
only. The model was told that a far paper may be used only to say what was found there, and in 2
of 8 answers it still applied one to the orchard ("Higher LST in your orchard may indicate…
[2]", a study of Alaskan tundra). As with citations and numbers (0005, 0006), an instruction to
a small model is not a guarantee.

The same day, OpenAlex's daily budget ran out during scoring, and both Magon's search and the
independent scorer stopped: one index was a single point of failure.

A third change was tried and not kept. The fit rating reads where a study was made, not what it
is about, so two off-topic papers from Mediterranean olive groves rated near. A rule requiring
the abstract to name both a vegetation signal and a driver or seasonal process was written after
labelling thirty abstracts for it (tests/data/fit_abstracts.json, field `relation`). It missed no
relevant paper among the thirty, but rejected only 3 of the 13 that do not study such a relation,
and on the controlled test's papers it would have rejected three relevant ones, among them the
olive review and the olive UAV study. A rule that throws good evidence away is worse than none,
as with the ranking cut-off of the evaluation ladder; topic is left to the ranker and reported
as a limit.

## Decision

- After the answer is written, `fit.flag_transfers` finds each sentence that cites a paper rated
  far and speaks of the researcher's own area or data (their area names, or "your orchard", "the
  data", "here"), and adds after it, in italics: "This applies a finding from a far setting
  ([n] place, on vegetation) to your data; it is not shown to hold here." Part headings are not
  read as the sentence. Nothing is removed.
- When OpenAlex cannot be reached or is out of budget, `search_papers` searches Crossref by
  words (journal articles, abstracts when Crossref has them). The independent scorer does not
  fall back (`fallback=False`), so every version it compares is scored against one index.
- The controlled test reports how many misapplied sentences code marked; the scorer leaves the
  mark out of the model's text, as it does the parts code writes. Both were decided before the
  run that measures them.

## Consequences

- A far paper applied to the researcher's data can still be written, but no longer reaches the
  researcher unmarked. Detection is by patterns: a sentence that speaks of the area in other
  words is missed.
- Crossref abstracts are often missing, so a fallback answer has less to read and the fit rating
  more often says "unknown". The researcher is not told which index answered; the log is.
- Off-topic papers from the researcher's own setting still pass the fit rating.
