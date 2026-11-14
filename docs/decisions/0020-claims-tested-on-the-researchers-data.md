# 0020. A claim from a paper is tested on the researcher's data, by code

Status: accepted

## Context
A literature assistant can say what a paper claims. Whether the claim holds where the
researcher works is a separate question, and their own series can answer it with analyses
Magonia already has: the lag explorer (correlation of anomalies at lags 1 to 12 months, a bound
corrected for autocorrelation and for testing several lags, as in the paper's notebook 03) and
the trend test (Theil–Sen slope, Mann–Kendall). No research assistant we compared has the
literature and an analysis engine on the same data, so none can do this.

## Decision
When the researcher asks to test a claim ("test this claim on my orchard: …"), code reads it
into what it asserts (vegetation variable, driver, direction, lag; or a long-term change),
runs the matching analysis on the first open area with the series it needs, and gives one of
four verdicts by fixed rules: replicates (beyond chance, with the claimed sign), contradicts
(beyond chance, opposite sign), undecided (not beyond chance; the lag that does stand out is
named) or cannot test. A claimed lag is matched within one month either side. "Drought lowers
NDVI" is read as NDVI rising with SPEI, since drought is low SPEI; the way the driver moves
("higher LST") is read apart from the verb ("reduces"). With no direction stated, the physical
expectation is tested, and the result says so. The model is given the verdict and reports it;
it does not reach one. The answer shows the verdict, the claim and what was tested in words.

## Consequences
The claim is read by code because a model misread the sign of SPEI in testing; the reading is
shown so the researcher can disagree with it. Only two kinds of claim are tested, and a
claim's drought index may be at another accumulation scale than the one open (said with the
verdict). A verdict is about this area and period, not the paper. Reading claims by patterns
will miss phrasings; each miss becomes a test.
