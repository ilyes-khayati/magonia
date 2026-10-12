# Development

## Workflow

1. Pick a card from **Ready** on the project board and move it to **In progress**
   (at most two cards in progress).
2. Create a branch named after the issue: `git switch -c <number>-<short-name>`.
3. Commit small, logical steps. Messages complete the sentence "this commit will…".
4. Run the checks locally from the package folder:
   `uv run ruff check .` and `uv run pytest`.
5. Push and open a pull request with `Closes #<number>` in the description.
6. Merge only when CI is green, with **squash and merge**, and delete the branch.
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