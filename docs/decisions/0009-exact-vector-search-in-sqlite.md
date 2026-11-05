# 0009. Exact vector search in SQLite, scoped to the answer's papers

Status: accepted

## Context
Magon ranks passages of papers and of the researcher's files by meaning, with 768-dimension
embeddings from nomic-embed-text.

## Decision
Embeddings are stored as BLOBs beside their passages in SQLite and compared by exact cosine
in numpy, only over the papers of this answer (at most six found, plus the researcher's
files): a few hundred vectors, about a millisecond. No vector database or index.

## Consequences
One file to back up, no service to run, no approximation. "Search everything I have ever
read" across thousands of papers would need an index (sqlite-vec or pgvector with HNSW) and
hybrid retrieval, since embeddings blur exact terms such as "MOD13Q1" or "SPEI-12".
