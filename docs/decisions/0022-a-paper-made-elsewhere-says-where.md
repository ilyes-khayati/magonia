# 0022. A paper made in another setting says where, and carries over in direction only

Status: accepted

## Context
Searching the literature before explaining the researcher's data (0021) did not make Magon's
explanations more often supported: 39% before, 37% after, scored independently on 48 answers
(explanation test, 15 Nov). Reading the answers showed why. Magon found real papers and
transferred their findings to the orchard: a paper whose NDVI was lowest in February explained
a July minimum in Tunisia, and monsoon crops in central India explained the orchard's delay
between drought and greenness. Each sentence was faithful to its paper, so the support check
passed it. The rules already asked the model to say in what setting each study was made; a
small model did not.

Whether a finding holds in another setting is the question of external validity. It has four
dimensions: the units studied, the treatment, the outcome and the context (Egami and Hartman,
2023). The direction of an effect carries over under weaker assumptions than its size; timing
and size are what a setting changes. Evidence syntheses in health appraise how well a study's
setting suits the decision at hand, with criteria that differ from one organisation to the
next (Weise et al., 2020), so there is no checklist to copy.

## Decision
Code reads a paper's setting from its title and abstract: the place (a country or region, and
its region), the climate when the abstract names one, and the vegetation. The researcher's
setting is where their areas lie, from their outlines, and the vegetation their names give.
A dimension read on both sides that does not match makes the paper's setting differ. A
dimension that cannot be read on either side is not compared, and a global study differs in
no place.

The model is given each paper's setting with its abstract, and told when it is not the
researcher's: to use it only for the direction of an effect, and to say where it was found.
After the answer, a sentence that cites a paper made elsewhere without naming its place, its
climate or its vegetation gets, after the citation, where it was found ("found in India, on
rice"). Nothing is withdrawn for its setting: the evidence is real; the researcher is told
where it comes from.

A question that asks to explain the researcher's data is now recognised when it names their
data in words a method question does not use ("the NDVI trend", "this orchard"), and "what
does the correlation … tell me" is a question about meaning: three of the twelve questions of
the explanation test had gone unsearched.

## Consequences
The setting is read by word lists, which miss what they do not list and can misread a word in
another sense; ten real abstracts, labelled before the reader ran, were read as labelled. The
place of a study is what its abstract names, not where its authors work. Only three of the four
dimensions are compared; the driver and the variable measured are not. The effect is measured
on a second set of why-questions written before this was built.
