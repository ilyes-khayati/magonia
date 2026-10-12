# 0004. Background jobs in the API process, storage in SQLite

Status: accepted

## Context
An Earth Engine request takes from a few seconds to over a minute, so the interface
cannot wait on a single HTTP call. Version 1 runs on the researcher's own computer
for one user, and needs to store areas, workspaces, jobs and results.

## Decision
Jobs run in a small thread pool inside the API process. A request returns a job
id at once; the interface asks for its status until it is done or failed.

Everything is stored in one SQLite file (Python's built-in `sqlite3`), in
`~/.magonia/` by default or the folder named by `MAGONIA_DATA_DIR`. Results are
cached by their provenance, so an identical request is answered without calling
Earth Engine again.

## Consequences
Nothing extra to install or run: no Redis, Celery or database server. Jobs still
running when the API stops are marked failed at the next start. Only one API
process can run, which suits a local, single-user version. Cloud deployment (v2)
replaces the thread pool with a real queue behind the same job endpoints, and
SQLite with a hosted database.
