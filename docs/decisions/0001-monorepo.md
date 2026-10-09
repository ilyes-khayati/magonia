# 0001. One repository for engine, API and web

Status: accepted

## Context
The engine, the API and the interface change together while the product is young.
Separate repositories would mean coordinating versions across three places.

## Decision
Keep `engine/`, `api/` and `web/` in one repository. The engine stays an
independent Python package with no dependency on the API or the web code.

## Consequences
One board, one history, atomic changes across layers. The engine can be split out
later if it is published on its own.
