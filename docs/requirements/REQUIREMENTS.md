# Software Requirements Specification

**Magonia** — agricultural remote-sensing research platform

| | |
|---|---|
| Version | 0.2, draft for supervisor review |
| Date | 8 October 2026 |
| Author | Ilyes Khayati |
| Supervisor | Dr. Oumayma Bounouh |
| Status | Requirements gathering. Not yet approved for development |

---

## 1. Introduction

### 1.1 Purpose of this document

This document describes what the platform must do, for whom, and under which constraints. It is written so that a developer, a designer or a researcher can read it without further explanation. It does not prescribe implementation details except where a decision has already been taken.

### 1.2 Product summary

A no-code research workbench for agricultural remote sensing. A researcher selects one or more areas on a map, chooses satellite and climate variables and a time window, prepares and analyses the data, fits models and inspects their explanations, all from an interface instead of code. Every analysis is built from interchangeable blocks, every result shows where it came from and how certain it is, and an AI assistant helps interpret results and find supporting literature when the researcher asks.

### 1.3 Definitions

| Term | Meaning |
|---|---|
| Area | A polygon, rectangle or uploaded geometry selected by the user |
| Block | One step of an analysis (for example "NDVI", "quality masking", "wavelet decomposition", "Random Forest") |
| Analysis chain | An ordered set of blocks applied to one or more areas |
| Workspace | A saved project containing areas, chains and results |
| Provenance | The record of data source, dates, processing and parameters behind a result |
| Guardrail | An automatic methodological check that warns the user about a likely error |
| Interpreter | The assistant role that explains the user's own results |
| Librarian | The assistant role that answers questions from scientific literature, with citations |
| EE | Google Earth Engine |
| SPEI | Standardized Precipitation-Evapotranspiration Index |
| QA | Quality assessment band supplied with satellite products |

### 1.4 Priority scheme

| Priority | Meaning |
|---|---|
| **Must** | Required for the first version (v1) |
| **Should** | Planned for v1 if time allows, otherwise v2 |
| **Could** | Desirable, planned for a later version |
| **Won't (now)** | Explicitly out of scope for the current releases |

---

## 2. Product vision

### 2.1 Problem

Researchers who study agriculture with remote sensing currently face three obstacles.

1. **Access requires code.** The most capable tool, Google Earth Engine, is used through JavaScript or Python. We assume that many agricultural researchers do not code or code little; this assumption is to be verified (assumption A-1, section 10).
2. **Existing no-code tools stop at extraction.** Services such as NASA AppEEARS and Climate Engine deliver data or monitoring maps, but not the analysis that follows: decomposition, lag and drought-memory analysis, models and their explanations.
3. **Analysis results are easy to over-trust.** Our own work on olive-orchard NDVI showed that three equally accurate models explain the same data differently, and that common attribution methods over-weight correlated variables. Researchers have no simple way to see how reliable a result is.

### 2.2 Mission

Help agricultural researchers turn satellite and climate data into understanding they can trust, without writing code and without hidden assumptions.

### 2.3 Vision

Any researcher, anywhere, can ask a question about land and crops and get an answer they can explain, defend and reproduce.

### 2.4 Geographic and social focus

The platform serves agricultural research in climate-stressed and under-monitored regions, starting with the Mediterranean basin and North Africa, where drought and heat are already affecting food security and where monitoring tools are fewer than in North America and northern Europe. Nothing in the design should prevent use elsewhere.

### 2.5 Principles

These principles decide trade-offs whenever requirements conflict.

1. **Trust first.** Every number shows where it came from, how it was processed and how uncertain it is.
2. **The researcher is in control.** This is a platform with AI, not an AI platform. The user builds the analysis; the assistant helps only when asked.
3. **Transparent by default.** Every result can show the code that produced it.
4. **Built for agriculture.** Depth in one domain rather than breadth across all of them.
5. **Calm surface, full depth.** A quiet, focused interface that still exposes every parameter to those who want it.

### 2.6 Positioning

| Tool | What it does | What it lacks for this audience |
|---|---|---|
| Google Earth Engine Code Editor | Full analysis over a vast catalogue | Requires programming |
| NASA AppEEARS | Extracts satellite data for areas without code | No analysis, models or interpretation |
| Climate Engine | No-code maps and time series for climate and monitoring | Monitoring focus; no models, explanation or assistant |
| **This platform** | No-code analysis from data to models and explanations, with provenance, uncertainty and an assistant | |

---

## 3. Users

### 3.1 Primary user: agricultural researcher

Works in a university, research institute or agricultural agency. Understands agronomy and has basic remote-sensing knowledge. Codes little or not at all.

- **Goals:** characterise vegetation dynamics of crops and regions; relate them to climate and drought; compare areas and periods; produce defensible results for publication.
- **Pains:** time lost writing and debugging code; uncertainty about whether a method was applied correctly; difficulty explaining machine-learning results.

### 3.2 Secondary users

- **Graduate students** learning the field, who benefit from the tutor role and from seeing the code behind each result.
- **Researchers who code**, who use the platform for speed and export the code to continue in their own environment.

### 3.3 Not targeted now

Farmers, agribusinesses and consumers. A simplified product for them is a separate, later project (section 9).

### 3.4 Core user journey (first ten minutes)

1. The researcher opens the platform and sees a map.
2. They select a place by searching, drawing one or more areas, or uploading a file.
3. They choose the variables they want, for example NDVI, land surface temperature and SPEI.
4. They set the time window.
5. Charts appear for each area, with the source and processing of every series shown alongside.
6. They add blocks (decomposition, comparison, model) and inspect the results.
7. If something is unclear, they ask the assistant about the result in front of them.

---

## 4. Functional requirements

### 4.1 Accounts and workspaces (ACC)

| ID | Requirement | Priority |
|---|---|---|
| ACC-01 | The user can sign in with a Google account. | Must |
| ACC-02 | The user can sign in with an institutional account (university single sign-on). | Could |
| ACC-03 | The user can sign in with ORCID. | Could |
| ACC-04 | The user can connect their own Google Earth Engine project, and the platform uses it for all data requests made on their behalf. | Must |
| ACC-05 | A user without an Earth Engine account can explore a demo mode built on pre-computed sample areas. | Should |
| ACC-06 | The user can create, rename, save, reopen and delete workspaces. | Must |
| ACC-07 | A workspace stores its areas, analysis chains, parameters and results. | Must |

### 4.2 Map and areas (MAP)

| ID | Requirement | Priority |
|---|---|---|
| MAP-01 | The map supports search by place name and coordinates. | Must |
| MAP-02 | The user can draw polygons and rectangles. | Must |
| MAP-03 | The user can create several areas in one workspace and name each one. | Must |
| MAP-04 | The user can upload areas as GeoJSON, KML or zipped shapefile. | Must |
| MAP-05 | The user can switch basemaps: satellite imagery, terrain, street map and a dark minimal map. | Must |
| MAP-06 | Drawing tools snap, show area size while drawing and allow vertex editing. | Should |
| MAP-07 | The user can group areas (for example "irrigated orchards") and analyse a group as one unit or as members. | Should |
| MAP-08 | The user can select areas from administrative boundaries or land-cover classes. | Could |
| MAP-09 | The map displays the selected variable as a layer for a chosen date. | Should |

### 4.3 Data (DATA)

| ID | Requirement | Priority |
|---|---|---|
| DATA-01 | The user chooses variables from a catalogue grouped by theme (vegetation, temperature, water and drought, climate, soil and terrain). | Must |
| DATA-02 | The v1 catalogue contains at least MODIS NDVI, MODIS land surface temperature and SPEI at user-selectable accumulation periods (section 6). | Must |
| DATA-03 | Values are aggregated over each area as an area-weighted mean, with the spatial standard deviation and pixel count reported per date. | Must |
| DATA-04 | Each variable shows its source product, version, spatial resolution, temporal resolution and licence. | Must |
| DATA-05 | The user can upload their own tabular data (for example yields or field measurements) linked to an area and dates. | Could |
| DATA-06 | The catalogue is extended with further variables listed in section 6. | Should / Could |
| DATA-07 | Data requests that cannot be served (area too large, missing coverage) produce a clear message stating the reason and the limit. | Must |

### 4.4 Time (TIME)

| ID | Requirement | Priority |
|---|---|---|
| TIME-01 | The user sets a start and end date for the analysis. | Must |
| TIME-02 | The user chooses the temporal resolution of results: native, monthly or seasonal. | Must |
| TIME-03 | The user can define named periods (for example "drought 2022–2024") and compare them. | Should |
| TIME-04 | The user can restrict analysis to months or growing seasons. | Should |

### 4.5 Preparation (PREP)

| ID | Requirement | Priority |
|---|---|---|
| PREP-01 | Preparation steps are chosen by the user. Recommended steps are selected by default and each shows a one-line reason. | Must |
| PREP-02 | Quality masking using the product's QA band, with the number of observations removed reported. | Must |
| PREP-03 | Gap filling by interpolation, with the filled dates marked. | Must |
| PREP-04 | Smoothing (for example Savitzky-Golay), optional. | Should |
| PREP-05 | Decomposition into trend and seasonal components, with a choice of method: none, wavelet (discrete Meyer and others, level chosen by target period), STL, and others listed in section 6. | Should (wavelet), Could (others) |
| PREP-06 | Anomalies relative to a user-chosen reference period. | Should |
| PREP-07 | No preparation step is applied without being visible in the analysis chain. | Must |

### 4.6 Analysis (ANA)

| ID | Requirement | Priority |
|---|---|---|
| ANA-01 | Descriptive statistics and seasonal climatology per area. | Must |
| ANA-02 | Comparison of the same variable across areas and periods on one chart. | Must |
| ANA-03 | Correlation and lag analysis between variables, computed on deseasonalised series by default. | Should |
| ANA-04 | Trend testing (Mann-Kendall, Sen's slope) and breakpoint detection. | Could |
| ANA-05 | Phenology metrics: start, peak and end of season, season length and amplitude. | Could |
| ANA-06 | Drought-memory analysis relating vegetation to drought indices over several accumulation periods. | Could |
| ANA-07 | Pixel-level maps of trends or anomalies within an area. | Could |

### 4.7 Models (MOD)

| ID | Requirement | Priority |
|---|---|---|
| MOD-01 | The user can fit machine-learning models, starting with Random Forest, XGBoost and Ridge regression, to forecast a chosen variable from chosen predictors and lags. The model catalogue is extensible (for example linear models, support vector regression, gradient-boosting variants). | Should |
| MOD-02 | Training and test periods are split by time, never at random; the default leaves the most recent period for testing. | Should |
| MOD-03 | Results report RMSE, R² and MAE against persistence and climatology baselines. | Should |
| MOD-04 | Results report a noise floor from repeated fits with different random seeds. | Should |
| MOD-05 | Hyperparameters can be left at tuned defaults or set manually. | Should |
| MOD-06 | Deep-learning models for time series (for example LSTM, GRU, temporal convolutional networks, transformers). | Could |

### 4.8 Explanations and trust (XAI)

| ID | Requirement | Priority |
|---|---|---|
| XAI-01 | Each fitted model can be explained with SHAP and permutation importance. | Should |
| XAI-02 | Drop-column importance is available for confirming whether a model needs a feature. | Could |
| XAI-03 | When several models are fitted, their explanations are compared and the level of agreement is shown. | Could |
| XAI-04 | Importances are shown with their variation across seeds, not as single numbers. | Should |

### 4.9 Visualisation (VIS)

| ID | Requirement | Priority |
|---|---|---|
| VIS-01 | Interactive time-series charts with zoom, hover values and toggling of series. | Must |
| VIS-02 | Overlaid comparison of several areas or periods. | Must |
| VIS-03 | Seasonal-cycle charts (values by month across years). | Must |
| VIS-04 | Uncertainty is drawn where it exists: spatial spread, seed variation, confidence intervals. | Must |
| VIS-05 | Every chart has a provenance panel showing sources, dates and processing. | Must |
| VIS-06 | Charts can be downloaded as image files and their data as CSV. | Should |
| VIS-07 | A focus mode hides everything except the current element: a chart, the map or an analysis panel. | Should |

### 4.10 AI assistant (AI)

The assistant is optional and appears only when the user opens it.

| ID | Requirement | Priority |
|---|---|---|
| AI-01 | **Interpreter.** Answers questions about the user's current results, using the computed numbers and provenance as its source, and refers to the specific chart or value it relies on. | Should |
| AI-02 | **Librarian.** Answers questions from a curated corpus of agricultural and remote-sensing literature, and every answer cites its sources with links. | Could |
| AI-03 | **Guardrail.** Methodological checks run as deterministic code (for example: correlating two seasonal series, predictors too correlated to attribute, test period overlapping training). The assistant only explains a triggered check and cites the reference behind it. | Should |
| AI-04 | **Tutor.** Explains concepts (for example what SPEI-24 means) at the user's level. | Could |
| AI-05 | The assistant declines questions outside agriculture, remote sensing and research methods. | Must (when the assistant exists) |
| AI-06 | The assistant states when it does not know, and never invents numbers or references. | Must (when the assistant exists) |
| AI-07 | The assistant can suggest blocks, but never adds or runs them without the user's confirmation. | Must (when the assistant exists) |
| AI-08 | **Team of agents.** The assistant is organised as several specialised agents that the user can call individually or together, like a research team: for example a librarian, a builder that proposes analysis chains, an interpreter and a methods reviewer (guardrail). A farmer-oriented agent belongs to the later farmer product. | Could |
| AI-09 | **Closed-access literature.** When a relevant paper is not open access, the librarian lists it with its reference and how it can be obtained, without using its content. | Could |
| AI-10 | **Personal library.** The user can upload their own papers, which the librarian then uses for that user only. | Could |

### 4.11 Reproducibility (REP)

| ID | Requirement | Priority |
|---|---|---|
| REP-01 | Every analysis chain can be exported as an executable Python notebook that reproduces its results. | Should |
| REP-02 | The same chain with the same inputs always gives the same results (fixed random seeds, versioned data products). | Must |
| REP-03 | A workspace records the platform version and data-product versions used. | Must |

### 4.12 Sharing (SHR)

| ID | Requirement | Priority |
|---|---|---|
| SHR-01 | The owner can share a workspace with colleagues as view-only or editable. | Could |
| SHR-02 | Comments can be attached to charts. | Could |

### 4.13 Export (EXP)

| ID | Requirement | Priority |
|---|---|---|
| EXP-01 | A summary of a workspace (charts, parameters, provenance) can be exported as a document. Exporting is secondary to exploring and discussing results. | Could |

---

## 5. Non-functional requirements

### 5.1 Trust and correctness (NFR-T)

| ID | Requirement |
|---|---|
| NFR-T1 | Each analysis block is covered by automated tests. |
| NFR-T2 | Each analysis block is validated against an independent reference implementation or published results, within stated numerical tolerances, before release. |
| NFR-T3 | Default settings follow documented best practice, and the reference for each default is recorded. |
| NFR-T4 | Every methodological guardrail is backed by a cited source. |

### 5.2 Performance (NFR-P)

| ID | Requirement |
|---|---|
| NFR-P1 | Interface actions respond within one second. |
| NFR-P2 | Data requests and computations longer than a few seconds run as background jobs, with progress shown and the interface remaining usable. |
| NFR-P3 | Results already computed for the same inputs are reused rather than recomputed. |
| NFR-P4 | Target times and maximum area sizes are set after load testing (open question O-6). |

### 5.3 Usability and design (NFR-U)

| ID | Requirement |
|---|---|
| NFR-U1 | Visual direction: calm, dark and minimal (reference: Endel), with technical depth and full control of parameters available (reference: Ableton). |
| NFR-U2 | Dark theme by default, with a light theme available. |
| NFR-U3 | Text and charts meet WCAG AA contrast. |
| NFR-U4 | Advanced parameters are hidden behind an expandable section, never removed. |
| NFR-U5 | A first-time user completes the core journey (section 3.4) without documentation. |

### 5.4 Security and privacy (NFR-S)

| ID | Requirement |
|---|---|
| NFR-S1 | Authentication uses standard protocols (OAuth 2.0 / OpenID Connect). |
| NFR-S2 | Earth Engine credentials are stored encrypted and used only for the owner's requests. |
| NFR-S3 | Workspaces and uploaded data are private unless the owner shares them. |
| NFR-S4 | Users can delete their account and all associated data. |

### 5.5 Portability and deployment (NFR-D)

| ID | Requirement |
|---|---|
| NFR-D1 | The platform runs as a web application in the cloud. |
| NFR-D2 | The platform can also be installed and run on a researcher's own computer. |
| NFR-D4 | All functionality is available through a documented API, so the platform can be used programmatically as well as through the interface. The API may be built first (open question O-10). |
| NFR-D3 | All components are containerised. |

### 5.6 Maintainability (NFR-M)

| ID | Requirement |
|---|---|
| NFR-M1 | The analysis engine is a separate package with a documented interface, used by the interface and by exported notebooks alike. |
| NFR-M2 | New blocks can be added without changing existing ones. |
| NFR-M3 | The data layer is abstracted so that sources other than Earth Engine can be added. |

### 5.7 Licensing and compliance (NFR-L)

| ID | Requirement |
|---|---|
| NFR-L1 | Earth Engine is used under its terms; non-commercial use requires each user's own registered project. |
| NFR-L2 | Each data product's licence and required citation are displayed and included in exports. |
| NFR-L3 | Literature in the librarian corpus is used only within its licence. Open-access papers may be indexed; closed-access papers are only referenced (AI-09) unless the user supplies them (AI-10). |

---

## 6. Data catalogue

| Theme | Variable | Product | Resolution | Cadence | Priority |
|---|---|---|---|---|---|
| Vegetation | NDVI, EVI | MODIS MOD13Q1 | 250 m | 16-day | Must |
| Vegetation | NDVI and other indices | Sentinel-2 | 10–20 m | ~5-day | Should |
| Vegetation | NDVI and other indices | Landsat 8/9 | 30 m | 16-day | Could |
| Temperature | Land surface temperature, day and night | MODIS MOD11A2 | 1 km | 8-day | Must |
| Drought | SPEI, 1–48 months | SPEIbase (CSIC) | 0.5° | monthly | Must |
| Water | Precipitation | CHIRPS | ~5 km | daily | Should |
| Climate | Air temperature, soil moisture, vapour-pressure deficit | ERA5-Land | ~9 km | hourly/monthly | Should |
| Water | Evapotranspiration | MODIS MOD16 | 500 m | 8-day | Could |
| Radar | Backscatter (all-weather) | Sentinel-1 | 10 m | ~6-day | Could |
| Land cover | Land-cover class | ESA WorldCover / Dynamic World | 10 m | annual / near-real-time | Could |
| Soil and terrain | Soil properties, elevation, slope | SoilGrids, SRTM | 250 m, 30 m | static | Could |

The cadence column gives each product's native time step. The user can analyse data at the native step or aggregate it to any coarser step (for example monthly or seasonal); a finer step than the product provides is not possible.

Decomposition methods: none; wavelet (Should); STL, BFAST, EMD (Could).

---

## 7. System overview

```
 Browser or desktop app (React, interactive map, charts)
            │
            ▼
 API service (Python, FastAPI) ─── Authentication (OAuth: Google, institutional, ORCID)
            │
            ├── Job queue and workers ── Analysis engine (Python package: preparation,
            │                            decomposition, analysis, models, explanations)
            │
            ├── Data layer ── Google Earth Engine (user's project) ; later other catalogues
            │
            ├── Database (workspaces, areas, provenance) ; result cache ; file storage
            │
            └── Assistant service ── language model ; literature index ; guardrail rules
```

Decisions taken: Python analysis engine as a separate package; React web interface with an interactive map; background jobs for long computations; containerised deployment; Earth Engine accessed through each user's own project.

Decisions open: cloud provider (Google Cloud, which hosts Earth Engine, or AWS); database and cache products; language-model provider; desktop packaging; open-source or proprietary licence.

---

## 8. Release plan

### 8.1 Version 1 (target: four to five weekly cycles)

A working end-to-end path on the researcher's own computer:

- Connect an Earth Engine project (ACC-04)
- Map with search, basemaps, several drawn or uploaded areas (MAP-01 to MAP-05)
- NDVI, LST and SPEI with quality masking and gap filling (DATA-01 to DATA-04, PREP-01 to PREP-03, PREP-07)
- Time window and resolution (TIME-01, TIME-02)
- Time-series, comparison and seasonal charts with uncertainty and provenance (VIS-01 to VIS-05, ANA-01, ANA-02)
- Workspaces saved locally (ACC-06, ACC-07)

**Acceptance:** for a reference area, the extracted NDVI, LST and SPEI series match an independent extraction within stated tolerances.

### 8.2 Version 2

Sign-in (ACC-01), decomposition, correlation and lag analysis, models with explanations and noise floors, interpreter and guardrails, code export, cloud deployment.

### 8.3 Later

Librarian, tutor, further data products, phenology, sharing, institutional sign-in, user data uploads, and a separate product for farmers and agribusiness.

---

## 9. Out of scope (now)

- A simplified product for farmers, agribusinesses and consumers
- Real-time alerting and operational monitoring
- Commercial use of Earth Engine through a shared platform account
- Mobile applications

---

## 10. Open questions for the supervisor

| ID | Question |
|---|---|
| O-1 | Which variables do you and your students use most, beyond NDVI, LST and SPEI? |
| O-2 | Which analyses take the most time today, and which would you most like to do without code? |
| O-3 | Which crops and regions should the first version be tested on? |
| O-4 | What area sizes are typical: single fields, orchards, districts or whole governorates? |
| O-5 | Do your projects need user-supplied data such as yields or field measurements? |
| O-6 | What waiting time is acceptable for a large analysis? |
| O-7 | Would your lab test early versions and give feedback? |
| O-8 | Which sources should the librarian's literature corpus include first? |
| O-9 | Do the researchers you work with code? (verifies assumption A-1) |
| O-10 | Should the first version be an API, a web application or both? |

**Assumptions to verify**

| ID | Assumption | How to verify |
|---|---|---|
| A-1 | Many agricultural researchers do not code or code little. | Literature on researchers' tool use; short survey of the supervisor's lab and contacts |

---

## 11. Risks

| Risk | Effect | Mitigation |
|---|---|---|
| Earth Engine quotas or terms change | Data requests fail or become costly | Abstract the data layer (NFR-M3); cache results |
| The assistant states incorrect facts | Loss of trust | Ground answers in computed results and cited literature; deterministic guardrails; refusal outside the domain |
| Scope grows faster than development | No usable version | Strict release plan (section 8); priorities enforced |
| Analysis errors in the engine | Wrong scientific conclusions | Reference-result acceptance tests (NFR-T2); automated tests |
| Large areas are slow | Poor experience | Background jobs, caching, stated limits |
