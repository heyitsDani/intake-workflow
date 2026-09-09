# Eval results

Three full live runs against the 31-record golden set. The first ran the
original prompts and exposed two bugs (details below); runs A and B ran
the fixed prompts, identical code, back to back. Only A and B are
comparable, so they are the headline table - reported as a range rather
than one number, see "why a range" below.

| metric | run A | run B |
|---|---|---|
| abstain recall (caught the right abstains) | 3/4 | 3/4 |
| abstain precision (abstains that were real) | 3/5 | 3/5 |
| service_line accuracy | 92% | 88% |
| complexity accuracy | 71% | 75% |
| routing top-1 accuracy | 83% | 79% |
| routing shortlist recall | 92% | 88% |

(One record per run failed on a malformed API response, unrelated to the
code - excluded from both runs' numbers, not silently guessed.)

## The first run (before the prompt fixes)

For the record, the pre-fix run's numbers: abstain recall 4/4, abstain
precision 4/11, service_line 100%, complexity 65%, routing top-1 90%,
shortlist recall 100% - but on only 20 graded records, not 24.

These are NOT better numbers, despite appearances, and they are not
comparable to the table above. The buggy verifier abstained on 7 records
it should have answered, and some of those withheld drafts contained
wrong service-line answers - so the wrong answers were hidden from
grading instead of counted. When the fix made the system commit to
answers on those records, the hidden mistakes became visible and gradeable
(e.g. ENQ-0037's wrong Strategy & Advisory call, present in every run,
only shows up as a scored miss post-fix). Same underlying behaviour,
honestly measured this time. That first run's real output was finding the
two bugs - see docs/DECISIONS.md for both fixes.

## Why a range, not a single number

31 records is a small eval set, and the pipeline itself has real run-to-run
variance from LLM sampling. The clearest example: `ENQ-0036`, a record
written specifically as a genuine coin-flip between two service lines
where the right answer is "abstain, I'm not confident" - abstained
correctly on one run, answered confidently and wrongly on the other, same
input, same code. Any single accuracy figure from a run this size should
be read as one sample, not a fixed truth. See docs/DECISIONS.md for the
full reasoning and the two prompt fixes made after the first live run
exposed real bugs (a verifier that discarded good answers over a weak
routing match, and a one-directional bias toward overestimating
complexity).

## What's working as designed

- Abstain caught all 4 distinct trigger types in the golden set across
  both runs: a jurisdictional legal-opinion request, an export-control
  question, an ethics/surveillance request, and the genuine low-confidence
  coin-flip case above.
- Routing shortlist recall (92%/88%) is meaningfully higher than top-1
  accuracy (83%/79%) in both runs - exactly the point of shortlisting
  instead of forcing one answer. Every top-1 miss still had the right lead
  as the other shortlist candidate.
