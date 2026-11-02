# Decision records

One short file per significant technical decision: context, decision, consequences.
Numbered in order; superseded records are kept and marked as such.

| # | Decision |
|---|---|
| [0001](0001-monorepo.md) | One repository for engine, API and web |
| [0002](0002-api-first.md) | Build the API before the interface |
| [0003](0003-earth-engine-per-user.md) | Earth Engine through each user's own project |
| [0004](0004-jobs-and-storage.md) | Background jobs in the API process, storage in SQLite |
| [0005](0005-citations-checked-by-code.md) | Citations are checked by code, not trusted from the model |
| [0006](0006-numbers-checked-by-code.md) | Numbers are checked by code |
| [0007](0007-interface-state-as-a-document.md) | Interface state as one JSON document per workspace; entities as rows |
| [0008](0008-content-addressed-results-cache.md) | A content-addressed results cache, with the engine version in the key |
| [0009](0009-exact-vector-search-in-sqlite.md) | Exact vector search in SQLite, scoped to the answer's papers |
| [0010](0010-soft-deletion.md) | Soft deletion with a 30-day purge |
| [0011](0011-chat-as-ndjson-events.md) | Chat as NDJSON events over a POST response |
| [0012](0012-questions-routed-by-code.md) | Questions routed by code to a reduced prompt and tool set |
| [0013](0013-mago-proposes-the-researcher-acts.md) | Mago proposes, the researcher acts |
| [0014](0014-local-open-weights-model.md) | A local open-weights model behind a one-method provider protocol |
| [0015](0015-files-and-citations-decided-by-code.md) | Which files and earlier citations a question is about is decided by code |
| [0016](0016-evaluation-ladder.md) | Evaluate against a ladder of systems with a shared evidence pool |

The reasoning behind each, with the alternatives and when they would win, is in the
architecture document.
