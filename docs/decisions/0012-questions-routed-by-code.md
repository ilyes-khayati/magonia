# 0012. Questions routed by code to a reduced prompt and tool set

Status: accepted

## Context
A small model given every rule and every tool follows fewer of them: it mixed workspace
numbers into literature answers and searched the literature for questions about the
researcher's own data.

## Decision
`route.py` classifies a question with regular expressions (chat, method, data, research,
general). Each kind gets only the rules, context and tools it needs; when signals disagree
the question is "general" and gets everything. Overrides: a question about the researcher's
own files is never small talk; a question asked from a card is about that card.

## Consequences
Transparent, instant, testable, and wrong in predictable ways; a wrong route degrades to
"general", not to failure. The patterns need maintenance as phrasings appear (the proposal
gate of #118 was such a case). With a stronger model, free tool choice may become reliable
and the router can shrink.
