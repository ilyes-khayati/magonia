# 0023. Each paper is rated for how well it fits, and each explanation is tested on the data

Status: accepted; the explanation tests are refined by 0025

## Context
Naming where a paper was made (0022) made misapplied evidence visible but did not raise the
share of supported explanations: 34% before, 33% after, on 16 questions written beforehand
(16 Nov). Six literature searches (17 Nov) pointed the same way. Searching more helps when an
answer exists but makes models worse at saying when it does not (Xie et al. 2026). Whether the
evidence suffices can be judged before writing (Joren et al. 2024; Chen et al. 2026). Evidence
synthesis compares each study with an explicit target and rates the evidence down for each
difference, rather than excluding it (Core GRADE 5, Guyatt et al. 2025). Automated
indirectness verdicts are weak (F1 0.3-0.4, Suster et al. 2023), while the plain facts a paper
states are read reliably (Konet et al. 2024). The strongest discovery agents pair each proposed
explanation with a test on the data (Kosmos, Mitchener et al. 2025; Popper, Huang et al. 2025).

## Decision
- Code keeps a record of each paper: its setting (0022), and the sensors and variables its
  abstract names (engine/fit.py).
- Code rates the record against the researcher's setting, field by field: near, partly, far or
  unknown, by a rule fixed before it was measured and written in the module.
- The model is given each paper with its record and rating, and told how a far paper may be
  used: only to say what was found there.
- The evidence check: when no paper found is rated near or partly, the model is told so with the
  papers, before it writes, and to say so first.
- An explanation is answered in parts: what the data show, what the papers found, and what it
  could mean here. Code adds whether the evidence fits, paper by paper, from the records.
- Each explanation that claim testing (#171) can read is tested on the researcher's series with
  the same rules, and code adds the verdicts.

## Consequences
- The comparison is shown, not judged: the researcher sees why a paper is near or far.
- The rating reads only what the abstract states; an abstract that names no place is unknown,
  and a wrong reading of a place gives a wrong rating (measured on 30 labelled abstracts).
- Measured with the controlled-evidence test (evaluation/controlled.py): fixed papers from a
  matching setting, other settings, off-topic, and mixed, labelled before any run.
