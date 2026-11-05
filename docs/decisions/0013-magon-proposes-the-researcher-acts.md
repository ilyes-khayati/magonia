# 0013. Magon proposes, the researcher acts

Status: accepted

## Context
An assistant that changes the workspace on its own (adds analyses, rewrites instructions)
takes decisions that belong to the researcher, and a small model's mistakes would land in
their work unseen.

## Decision
Magon can only propose: an analysis or a standing instruction appears as a card with "Add it"
or "Save", and nothing changes until the researcher clicks. Code validates a proposal
against the workspace (does the area exist, is the variable known) and sends an invalid one
back to the model. The proposal tool is offered only when the message asks for something to
be done, and a one-variable analysis is of the variable the question names.

## Consequences
Every change to the workspace is the researcher's, and undoable. One more click per action;
proposals the researcher ignores cost nothing.
