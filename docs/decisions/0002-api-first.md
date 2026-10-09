# 0002. Build the API before the interface

Status: accepted

## Context
The specification allows the product to be an API, a web application or both
(NFR-D4, O-10). The interface will be a client of the same operations anyway.

## Decision
Version 1 delivers the engine and a documented API first (cycles 1-2). The web
interface is built on top of that API (cycle 3).

## Consequences
Every feature is testable without a browser, and other tools can use the
platform directly. The first visible interface arrives later in the version.
