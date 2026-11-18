# 0025. An explanation is tested by trying to falsify what it implies

Status: accepted (refines 0020)

## Context

Claim testing (0020) judged an explanation such as "NDVI falls with LST one month earlier" by
one test: the correlation of the two anomaly series near the claimed lag, against a bound
corrected for autocorrelation and for twelve lags. That test was calibrated against records
with no link (0.4% false confirmations) but not against the ways a correlation is produced
without the claimed cause. Two are common in vegetation records. Surface temperature follows
vegetation (it rises when vegetation browns), so last month's temperature shares the
vegetation's memory and seems to lead it. Two series that both drift over 25 years correlate
at every lag.

The strongest discovery agents test a hypothesis through several of its implications rather
than one (Popper, Huang et al. 2025, arXiv:2502.09858), and the survey of scientific
assistants done on 18 November found no assistant that tests literature-derived explanations
on the user's own data.

## Decision

When an explanation says which way the driver acts, code tests four implications, fixed in
advance (engine/falsify.py): the anomalies are linked at the claimed lag; beyond the
vegetation's own memory of the month before (partial correlation); in both halves of the
record; and not through a shared linear trend. Each is a one-sided Fisher-z test on the
effective sample size of Bretherton et al. (1999), at alpha divided by the lags searched (3
around a claimed lag, 12 when none is claimed). The explanation replicates only if all four
pass: an intersection-union test, of level alpha under any dependence (Berger and Hsu 1996).
Merging e-values (Vovk and Wang 2021), as Popper does for an open sequence of generated tests,
was not used: with a fixed set that must all hold, it would let one strong implication carry a
failed one. The answer names each implication with its correlation, and which ones failed.

## Consequences

Measured before and after on simulated records, with a plan committed before the code
(evaluation/falsification_plan.md; results in the capstone's evaluations folder):

| Truth | Single test: replicates | Falsification: holds |
|---|---|---|
| no link | 0.3% | 0.1% |
| feedback (driver follows vegetation) | 97.5% | 3.7% |
| shared trend, no link | 81.6% | 1.9% |
| link r = 0.25 / 0.35 at lag 1 | 35.4% / 78.8% | 19.2% / 55.4% |

On the 500-orchard calibration of 0020, a link at another lag than the one claimed now
confirms the claim 2.2% of the time instead of 11%, and a real link of r = 0.35 is confirmed
43.6% of the time instead of 78.6%. Specificity was bought with power: a weak real link is now
more often "undecided", which is the honest outcome for a researcher, who is told which
implication failed. On the reference orchard, NDVI with LST and with SPEI-3 at one month both
hold; the LST link falls from r = -0.41 to -0.14 once NDVI's own memory is accounted for, so
most of the raw correlation is shared memory. Claims with no stated direction keep the single
test.
