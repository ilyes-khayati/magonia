# 0011. Chat as NDJSON events over a POST response

Status: accepted

## Context
An answer takes from seconds to two minutes and passes through stages the researcher should
see: the route, the search, the papers, the passages read, the text, a proposal, the checks.
The question carries a view of what is open, several kilobytes.

## Decision
`POST /conversations/{id}/chat` answers with one JSON object per line (NDJSON), read with
`fetch` and a stream reader; the client applies each event with a pure reducer
(`applyEvent` in `chat.ts`). The API pulls events until the first that needs the model, so
an unreachable model fails with a 503 before streaming starts. The answer is saved in a
`finally` block.

## Consequences
Server-Sent Events were rejected because `EventSource` only does GET; WebSockets because
nothing flows from the client during an answer. A broken connection loses the rest of the
stream, though the saved answer is shown when the conversation is reopened.
