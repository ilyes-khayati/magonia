# 0017. Each workspace has its own files; the paper cache is shared

Status: accepted

## Context
A PDF added in one workspace appeared in every other, and Mago read it there: a field
survey of Jendouba showed up while studying Sfax.

## Decision
An upload belongs to the workspace it was added in (`uploads.workspace`). Listing, adding and
the chat use `Library.scoped(workspace)`. Papers found by searches, their passages and the
kept PDFs stay shared across workspaces: they are a cache, and the same paper reads the same
anywhere. Files added before this go to the first workspace whose library is opened.

## Consequences
What Mago can cite in a workspace is what that workspace holds. The same PDF added to two
workspaces is stored once on disk, but read and embedded twice.
