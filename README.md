# Magonia

A research workbench for agricultural remote sensing. A researcher draws or uploads the
fields they study, picks satellite and climate variables, and follows the work from the
data to analyses, forecast experiments and the literature, without writing code. Every
number shows where it came from.

Named after Mago of Carthage, whose 28-book treatise on agriculture Rome had translated
after the city fell, and after Magonia, the medieval kingdom in the sky. **Mago** is also
the name of the research assistant inside it.

![An olive orchard and a cereal field near Jendouba, Tunisia: monthly NDVI and land surface temperature, 2020–2024](docs/images/workbench-light.jpg)

## What it does

The pages follow the order of the research. They are in the rail on the left.

| Page | What the researcher does there |
|---|---|
| **Map** | Draw polygons or rectangles, upload GeoJSON, KML or zipped shapefiles, search places; areas are checked and measured |
| **Data** | 14 variables through Google Earth Engine: vegetation indices (NDVI, EVI, SAVI, NDMI, NBR), LAI, FPAR, GPP, evapotranspiration (MODIS), land surface temperature, air temperature, rain and soil moisture (ERA5-Land), and the SPEI drought index. Cloud filtering, monthly or seasonal means, gap filling with filled values marked, and each step's reason shown |
| **Analyses** | Correlation and lag, trend and season, long-term trend (Mann–Kendall), season dates, memory and lags; each can be renamed, duplicated and exported as a Jupyter notebook that reproduces it |
| **Model** | Forecast experiments with Ridge, Random Forest and XGBoost, tuned on the training years only, scored against a noise floor, with what each model relies on |
| **Board** | Pinned charts and results, with the researcher's notes |
| **Library** | The researcher's own PDFs (each workspace has its own) and standing instructions for Mago |
| **Mago** (⌘J) | Answers from the workspace's own numbers, the researcher's files and the open literature (OpenAlex), and proposes analyses that run only on a click. Its citations and numbers are checked by code, not trusted |

Nothing is lost: deletions can be undone (⌘Z), and deleted workspaces and conversations
are kept for 30 days.

**Trust, measured.** An acceptance test checks that Magonia reproduces an independent
extraction for a reference orchard, exactly. The evaluation harness (`engine/evaluation/`)
measures Mago against the bare model it runs on; results and their limits are in the
architecture document, chapter 9.

![The same workspace in the dark theme, showing seasonal cycles](docs/images/workbench-dark.jpg)

## Running it

Requires Python 3.12+, [uv](https://docs.astral.sh/uv/), Node 24 (`.nvmrc`) and, for Mago,
an [Ollama](https://ollama.com) server with `qwen2.5:7b` and `nomic-embed-text`.

```bash
cp .env.example .env    # then fill in your values; every variable is explained there

# once: sign in to Earth Engine (free for research; see code.earthengine.google.com/register)
uv run --directory engine earthengine authenticate

# terminal 1: the API on http://127.0.0.1:8000 (endpoints documented at /docs)
cd api && uv sync && uv run uvicorn api.main:app --reload

# terminal 2: the interface on http://localhost:5173
cd web && npm install && npm run dev
```

The first time, Magonia asks for your Earth Engine project id and checks that it answers.
Workspaces, areas, results and the library are kept in `~/.magonia/`. Without an Ollama
server, everything works except Mago; `MAGONIA_MODEL_URL=scripted` gives fixed answers.

## Structure

| Folder | Contents |
|---|---|
| `engine/` | Python package, no web code: extraction, preparation, analyses, models, Mago's pipeline and its checks |
| `engine/evaluation/` | The evaluation harness: 52 cases, four systems, scorer and report |
| `api/` | FastAPI service: workspaces, background jobs, the results cache, the library, Mago's streamed answers |
| `web/` | React interface: the pages above |
| `docs/requirements/` | Software requirements specification |
| `docs/decisions/` | Architecture decision records |
| `docs/DEVELOPMENT.md` | Workflow, tests, evaluation and troubleshooting |

## Planning

Work is tracked on the GitHub project board in cycles; each issue references a requirement
ID from the specification (for example `MAP-02`). Next: sign-in and cloud deployment, and
Mago's evaluation on a second, independent case set.
