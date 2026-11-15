# 0021. An explanation of the researcher's data comes from papers, or is labelled as Magon's own

Status: accepted

## Context
On a question about the researcher's data, Magon's numbers were checked against what code
computed, but its explanations were not. Asked why the orchard greens so fast, it said olive
leaves have a short lifespan, which is false: olive is evergreen. Nothing searched for the
mechanism and nothing checked the sentence. Giving Magon facts about crops would hide the
failure rather than fix it: Magon would look right because it was told the answer, and an
evaluation of it would measure what it was given. Separately, a sentence such as "studies have
shown that…" or "a 2019 study in Kairouan found…" names no author, so the author–year check
never saw it.

Factuality research checks long answers claim by claim, and only the claims that can be
checked (FActScore, Min et al. 2023; VeriScore, Song et al. 2024). Evidence is best gathered
while answering rather than looked for afterwards.

## Decision
A question on the data that asks why, or what the data mean, is an explanation. Code searches
the literature on the question's words before the model answers, and the model is told to keep
what the data show apart from why, and to say when a point is its own reasoning. After the
answer, every sentence that cites nothing is checked against the papers found, as in a
literature answer, except a sentence whose numbers code computed: that one is a fact of the
data, checked as a number. A sentence no paper bears out is shown as Magon's own reasoning.

A sentence that says what research found, with no paper found or given for the answer, is
withdrawn whatever the setting: nothing Magon read says it.

## Consequences
Magon is given no facts about crops or findings; what it explains, it explains from papers it
found, or says is its own. An explanation takes a search longer. The labels are as good as the
uncited check: "own reasoning" can mean wrong, or true but not in the papers found (the same
limit VeriScore states). "Studies show" is recognised by patterns, which will miss phrasings.
