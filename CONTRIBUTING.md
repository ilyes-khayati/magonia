# Contributing

Magonia is a research tool, and contributions from researchers and developers are welcome:
bug reports, new variables or analyses, better wording, and fixes.

## Reporting a problem or an idea

Open an issue. For a bug, say what you did, what you expected and what happened, and include
the area and variables involved when the problem is in the data.

## Changing the code

1. Fork the repository and create a branch: `git switch -c <short-name>`.
2. Set it up as in the README's **Running it**.
3. Make small, logical commits.
4. Before opening a pull request, run the checks:
   - `engine/` and `api/`: `uv run ruff check .` and `uv run pytest`
   - `web/`: `npm run lint`, `npm test` and `npm run test:e2e`
5. Open a pull request that explains what changes for a researcher using Magonia.

[`docs/DEVELOPMENT.md`](docs/DEVELOPMENT.md) covers the tests, the evaluation of Magon and
troubleshooting. [`docs/decisions/`](docs/decisions/) explains why the architecture is the way
it is; read the relevant record before changing that part.

## Licence

By contributing, you agree that your contribution is licensed under the
[GNU Affero General Public License v3.0](LICENSE), like the rest of Magonia.
