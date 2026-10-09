# Agri Workbench

A research workbench for agricultural remote sensing. Researchers pick places on a
map, pull satellite and climate data, and build analyses from blocks, without
writing code. Every result shows where it came from.

Working name. Early development.

## Structure

| Folder | Contents |
|---|---|
| `engine/` | Python package: data access, preparation, analysis |
| `api/` | FastAPI service exposing the engine |
| `web/` | React interface with the map (from cycle 3) |
| `docs/requirements/` | Software requirements specification |
| `docs/decisions/` | Architecture decision records |

## Development

Requires Python 3.12 and [uv](https://docs.astral.sh/uv/).

```bash
cd engine && uv sync && uv run pytest
cd api    && uv sync && uv run pytest
uv run --directory api fastapi dev src/api/main.py   # http://127.0.0.1:8000/docs
```

Earth Engine access uses your own Google Cloud project:

```bash
uv run --directory engine earthengine authenticate
```

## Planning

Work is tracked on the GitHub project board in weekly cycles. Each issue references
a requirement ID from the specification (for example `MAP-02`).
