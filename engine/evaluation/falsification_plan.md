# Falsification of explanations: test plan (written before the code)

18 November 2026. Written and committed before `engine/falsify.py` exists and before any run.

## What is being changed

Today an explanation such as "NDVI falls with LST one month earlier" is tested on the researcher's series by a single test (ADR 0020). The test is the correlation of the two anomaly series at the claimed lag (±1 month), against a bound corrected for autocorrelation (Bretherton et al., 1999) and for twelve lags (Bonferroni).

The new step treats the explanation as a hypothesis with several observable implications, after Popper's agentic falsification (Huang et al., 2025, arXiv:2502.09858). Each implication is a pre-specified test, from a fixed set:

1. **Linked:** the anomalies correlate at the claimed lag with the claimed sign.
2. **Beyond the response's memory:** the link remains once last month's response anomaly is controlled for (partial correlation). A driver that merely follows vegetation can otherwise appear to lead it.
3. **In both halves of the record:** the link has the claimed sign and passes in the first and the second half separately.
4. **Not a shared trend:** the link remains after a linear trend is removed from both series.

The explanation "holds on the data" only if every implication passes. This is an intersection–union test, whose level is α under any dependence between the component tests (Berger and Hsu, 1996, Statistical Science 11(4)). Each component is a one-sided Fisher-z test at α divided by the number of lags searched:
- 3 when the claim states a lag;
- 12 when it does not.

The sample size is the effective one of Bretherton et al. (1999).

"Contradicted" means implication 1 passes with the opposite sign. "Not shown" means anything else, and the implications that failed are named.

e-values were considered: calibrated p-values merged by averaging, as in Vovk and Wang (2021, Ann. Statist. 49(3)). They were not used. With a fixed set of implications that must all hold, the intersection–union test is exact. An average of e-values would let one strong implication carry a failed one, which is not falsification.

## Pre-registered evaluation (simulation; no language model involved)

Harness: `evaluation/falsification_calibration.py`.
- 1,000 synthetic records per scenario.
- 300 months of an NDVI-like series: a yearly cycle plus AR(1) anomalies. The driver is AR(1), with φ = 0.8 like SPEI, or φ = 0.5 like LST.
- The claimed lag is 1 month, the claimed sign negative, and α = 0.05.

Scenarios:

| Scenario | Truth | Current single test should | New test should |
|---|---|---|---|
| S0 | no link | replicate ≤ 5% | hold ≤ 5% |
| S1 | link r = 0.25 at lag 1 | (power) | (power) |
| S2 | link r = 0.35 at lag 1 | (power) | (power) |
| S3 | **feedback:** the driver follows this month's vegetation (driver_t = c·NDVI_t + noise), with no effect of the driver on vegetation | may replicate (spurious) | hold ≤ 5% |
| S4 | **shared trend:** both series trend over 25 years, with no link | may replicate (spurious) | hold ≤ 5% |

Primary measures:
- the rate of "replicates" (current) and "holds" (new) in each scenario, with 95% Monte Carlo intervals;
- the change in power between the two procedures in S1 and S2.

Pass criteria:
- In S0, S3 and S4, the upper end of the 95% interval of "holds" is at most 0.05 plus Monte Carlo error.
- In S1 and S2, the power is reported whatever it is. A loss of power is the expected price and will be stated.

Secondary measure: the verdict on the reference orchard's real series for the two relations tested most often on 17 November (NDVI with LST and with SPEI-3 at lag 1). This is reported, not judged.

Nothing in this plan will be changed after the first run. Any later change will be listed below with its date and reason.

## Changes after the first run

None to the plan. After the first run the test was also wired into claim testing (claims.lag_test), and the
500-orchard calibration of ADR 0020 was re-run with it; both results are in ADR 0025.

Deviations and limits, recorded after a review on 18 November:
- The plan was committed four minutes before the code and the first run: it fixed the design before any
  result, but it was written by the person who then wrote the code, the same morning.
- The plan names two driver memories (φ = 0.8 like SPEI, φ = 0.5 like LST). S0–S2 were run with φ = 0.8 only;
  φ = 0.5 appears only as the driver's own noise in S3.
- S3's 95% interval (2.7–5.1%) passes the criterion "at most 0.05 plus Monte Carlo error" only because its
  upper end already contains that error; read strictly, S3 is at the 5% level, not clearly below it.
- For a claimed lag of 1 month, the lags searched are 1 and 2 (no lag 0), so each implication is tested at
  alpha / 2, not alpha / 3.
- Wiring the test into claims.lag_test made the "current single test" column of the harness run the new
  test too; claims.lag_test(single=True) now keeps the single test, and the harness uses it, so the table
  above can be reproduced.

## Results of the first run (1,000 records per row, seed 20261118)

| Scenario | Current test: replicates (95% CI) | Falsification: holds (95% CI) |
|---|---|---|
| S0 no link | 0.3% (0.1–0.9) | 0.1% (0.0–0.6) |
| S1 link r = 0.25 | 35.4% (32.5–38.4) | 19.2% (16.9–21.8) |
| S2 link r = 0.35 | 78.8% (76.2–81.2) | 55.4% (52.3–58.5) |
| S3 feedback | 97.5% (96.3–98.3) | 3.7% (2.7–5.1) |
| S4 shared trend | 81.6% (79.1–83.9) | 1.9% (1.2–2.9) |

Pass criteria: S0, S3 and S4 are at or below 0.05 within Monte Carlo error (S3's upper bound, 5.1%, is within
it). The loss of power in S1 and S2 is stated, as planned.
