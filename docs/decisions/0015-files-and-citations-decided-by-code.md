# 0015. Which of the researcher's files and earlier citations a question is about is decided by code

Status: accepted

## Context
"The paper I uploaded", "the second file" and "the first study you cited" are references a
small model resolves badly: it asked for the title of a file it had been given.

## Decision
Code resolves them (`awareness.py`): files by name, by position or by speaking of one's own,
without a similarity threshold; earlier answers' papers carried in the history and given
again with new numbers. The passages of the files asked about go right before the question,
where a small model reads them (#117).

## Consequences
Measured: the own-file cases went from 1/3 to 3/3. File text near the question is where an
injected instruction is most persuasive; it is framed as passages to answer from, and the
hidden-instruction case is part of the evaluation.
