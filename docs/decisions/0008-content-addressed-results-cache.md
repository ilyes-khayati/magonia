# 0008. A content-addressed results cache, with the engine version in the key

Status: accepted

## Context
Extracting a series from Earth Engine takes seconds to minutes and costs quota. A workspace
reopened months later should show the same numbers without asking again.

## Decision
A result is stored under a 16-hex hash of everything that determines it: variable,
geometry, dates, masking, scale, time step, gap rule and `engine.__version__`. Equal inputs
mean an equal output, so the output is named by its inputs (as git objects or Bazel's action
cache are). The cache is shared across workspaces.

## Consequences
Deduplication, reproducibility and safe concurrency (two writers of one key write the same
value). The precondition is that every input is in the key. The engine's code is in it only
through the version string, so `test_cache_guard.py` fails whenever the code behind cached
results changes, until the version is bumped. Earth Engine's own reprocessing of MODIS is
not in the key; that is an accepted risk.
