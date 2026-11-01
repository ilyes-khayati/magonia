# 0007. Interface state as one JSON document per workspace; entities as rows

Status: accepted

## Context
Some things in a workspace have identity and relationships: areas are referenced by jobs,
messages belong to conversations. Others are interface state that is only ever read and
written whole by one client, and whose shape changes almost every week: the analyses, the
forecast experiments, the board, the layout.

## Decision
Rows for entities (workspaces, areas, jobs, conversations, messages). One JSON document,
`workspaces.settings`, for interface state. The client owns that document's schema and
validates what it reads: unknown analysis kinds are dropped, old forecast cards upgraded.

## Consequences
A new kind of analysis needs no migration. The server cannot query inside the document,
and nobody needs it to: Mago learns about analyses from the view the client sends. A
document written whole means the last writer wins, which is safe for one researcher but
not for two editing one workspace; then: rows with a version column, or a CRDT document.
