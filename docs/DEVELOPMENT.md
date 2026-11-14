# Development

## Workflow

1. Pick a card from **Ready** on the project board and move it to **In progress**
   (at most two cards in progress).
2. Create a branch named after the issue: `git switch -c <number>-<short-name>`.
3. Commit small, logical steps. Messages complete the sentence "this commit will…".
4. Run the checks locally from the package folder:
   `uv run ruff check .` and `uv run pytest`.
5. Push and open a pull request with `Closes #<number>` in the description.
6. Merge only when CI is green, and delete the branch. A single pull request: **squash and
   merge**. Pull requests stacked on one another: **merge commit** (`gh pr merge N --merge`),
   because squashing the first one makes the next one conflict with `main`.
7. Back on `main`: `git switch main && git pull`.

`main` is never committed to directly.

## Tests

- Unit tests must not need network access or credentials. Fake external services
  (see `engine/tests/test_earth_engine.py`).
- Tests that call real services are marked `@pytest.mark.live`. They are skipped by
  default and run locally with `uv run pytest -m live`.
- `engine/tests/test_acceptance.py` checks that Magonia reproduces the reference
  extraction for the Jendouba orchard. CI replays Earth Engine responses stored in
  `engine/tests/data/recorded/`. After changing the extraction code, run the live
  version (`uv run pytest -m live tests/test_acceptance.py`), then re-record with
  `uv run python scripts/record_responses.py`.
- `engine/tests/test_cache_guard.py` fails when the code behind cached results
  (extraction, preparation, forecasting) changes. Results are cached by request and
  `engine.__version__`, so if a change can alter a result, bump the version; then copy
  the new hash the test prints into it.

- `web/e2e/` drives the interface in a browser against a faked API (`npm run test:e2e`).

## Evaluating Magon

`engine/evaluation/` asks 52 cases to four systems on the same model (the bare model, the
model with Magon's rules, the pipeline on abstracts, the full pipeline) and scores them:

```bash
cd engine
uv run python evaluation/run.py results/ --repeats 2        # needs the Ollama server
uv run python evaluation/score.py results/ && uv run python evaluation/report.py results/
```

The scorer judges whether the literature supports each statement with MiniCheck-RoBERTa
(decision 0019); `--judge model` asks the chat model instead, as the earliest runs did, and
the report names the judge next to the figure. Verdicts are cached per judge.

To compare a change with an earlier run on the same papers, replay its searches:
`MAGONIA_REPLAY=results/raw.jsonl uv run python evaluation/run.py after/ --systems magonia`.
Read the failures in `report.md` by hand before trusting a number: some will be faults of
the case or of the scorer.

Magon checks each cited sentence against its passages with a verifier, a small model that
runs on the CPU of the machine serving the API (decision 0019). Install it there, once:

```bash
cd api && uv sync --extra verify     # about 2.5 GB with the model weights, downloaded on first use
```

Without it the chat model judges its own sentences, and Settings says so. To re-measure the
verifiers' thresholds on SciFact:
`cd engine && uv run --extra verify python evaluation/verifiers.py OUT --scifact DATA`.

## Configuration

Settings that differ per machine live in `.env`, which is never committed.
`.env.example` lists every variable. Copy it to `.env` and fill in your values.

## Decisions

Significant technical choices get a short record in `docs/decisions/`.

## Troubleshooting

`ModuleNotFoundError: No module named 'engine'` on macOS: iCloud Desktop sync
marks files in `.venv` as hidden, and Python 3.13 skips hidden `.pth` files.
Each `.venv` is a symlink to `.venv.nosync`, which iCloud ignores. To recreate one:
`rm -rf .venv && mkdir .venv.nosync && ln -s .venv.nosync .venv && uv sync`.