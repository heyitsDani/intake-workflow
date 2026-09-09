# Decisions log

Running record of choices made, alternatives rejected, and why. Written as I go,
so the panel conversation is answered from reasoning rather than reconstruction.

(Moved here from `data/DECISIONS.md` partway through - this is the path named in
`CLAUDE.md`'s working agreement and in `README.md`'s own directory tree; `data/`
should hold data artifacts, not the log.)

---

## Framing

**2026-09-08 - Scoped to the stated volume, not a generic pipeline.**
40-60 enquiries/week is ~2,600/year, so one LLM call per enquiry costs single-digit
dollars annually and latency is irrelevant. Rejected: vector store, fine-tuning,
message queue, served API, Docker, a database. Would add a queue and a real datastore
somewhere north of ~5,000/week or if intake became customer-blocking; not before.

**2026-09-08 - Value case is not labour saved.**
8 hrs/week ~= 0.2 FTE ~= $10-15k/yr, which does not justify an engagement. Reframed the
win as routing accuracy, speed-to-first-response on inbound leads (revenue, not cost),
and structured demand data the firm currently doesn't have because it lives in one
analyst's head. Rejected the brief's own framing of "replacing the manual step" as the
end state - that is compression without redesign.

**2026-09-08 - No baseline exists, and said so rather than inventing one.**
Brief asserts the current process is "error-prone" with no number. Cannot claim
improvement against an unmeasured baseline, and historical analyst labels are
contaminated ground truth, so they can't be used for training or scoring either. Would
establish a real baseline in week one via dual-labelling before any deployment claim.

**2026-09-08 - Deliverables: prototype + half-page write-up; architecture doc reduced
to a single diagram.** Depth-over-breadth was explicit in the brief, and the write-up
questions (what breaks first, what to monitor, what's the fallback) are the panel's
agenda handed over in advance. At this scale an honest architecture is four boxes;
two pages on four boxes reads as padding.

---

## Modelling

**2026-09-08 - Treated the three outputs as separate problems, not one prompt call.**
Service line is closed-set and recoverable from text. Complexity is subjective with no
ground truth and is where the analyst's tacit knowledge actually sits. Routing depends
on org state (lead specialty, current load, prior client relationship) the form does
not contain. Collapsing them into one call is the likely default and loses all three
distinctions.

**2026-09-08 - Routing treated as rules + capacity, not pure classification.**
Two leads per service line for most lines, differentiated by specialty (e.g. ERP vs
analytics within Technology & Data), so routing cannot be a lookup from service_line.

**2026-09-08 - System must be able to abstain, with two distinct triggers.**
(a) Low confidence - the ordinary case. (b) Recognised-but-above-authority - request is
understood well enough to know it needs partner/engagement-risk review. Most
implementations only build (a). If the prototype ships with only (a), that gap is stated
explicitly rather than left looking like an oversight.

**2026-09-08 - Abstain mechanism: a single separate verifier call, not per-stage
confidence.** RESOLVES the earlier open item ("confidence threshold mechanism not yet
chosen"). Considered three options: (1) self-reported confidence per stage - cheapest,
but known poorly calibrated and blind to confidently-wrong answers; (2) self-consistency
ensemble (N calls, abstain on disagreement) - better-calibrated signal, trivial extra
cost at this volume, more code; (3) a separate verifier call reviewing the whole
assembled decision against the source text, returning `sign_off`, `reason`, and
`abstain_trigger` (`low_confidence` | `above_authority` | null). Chose (3): it directly
implements both named abstain triggers above in one place, and reviewing the whole
decision (not just one stage) catches cross-stage inconsistency - e.g. a routing
candidate implying ERP work the text never mentions.
**Known tradeoff, flagged for the panel**: one whole-decision verifier loses per-stage
attribution. If it flags a problem, the log says something looked off, not which of the
three stages was actually wrong. The chosen pipeline is 3 LLM calls per enquiry
(service_line, complexity, one verifier); an independent verifier per stage would raise
that to 5 (adding a dedicated verifier for each of service_line, complexity, and the
routing shortlist) - not worth it at this volume, but worth naming as the reason
accuracy debugging will sometimes require reading the transcript by hand rather than
trusting the log alone.

**2026-09-08 - Routing is rules, not a model call, and structurally never
autonomous.** A static lead-roster table (lead -> service line(s) -> specialty keywords,
built from the specialty distinctions already articulated in `evals/golden.jsonl`
rationale, e.g. "Patel has the ERP background, Okonkwo's practice is analytics") returns
a shortlist of 1-2 candidate leads with rationale. A human analyst always makes the
final pick. This is deliberately not confidence-gated the way service_line/complexity
are: capacity and prior-relationship state never appear on the form, so a forced
single-name answer is a guess wearing the appearance of a decision. The system's job is
a good shortlist, not a verdict - which also means "fallback when the model gets it
wrong" for routing specifically is not a fallback, it's the default behaviour.
Rejected: a third LLM call to pick one specific lead (opaque for what is fundamentally a
lookup, and needs its own eval slice to trust); confidence-gated auto-assignment
(implies the system can know something about capacity that it structurally cannot).
**Known tradeoff, flagged for the panel**: keyword-based rules are brittle to phrasing
the table doesn't anticipate. Mitigated by the human always confirming rather than the
system ever acting alone, but a rule that's stale or too narrow will silently produce a
worse shortlist, not an error - this is the same "silent misroute" risk as the rest of
the system, one level down.

**2026-09-08 - Corrected the verifier prompt after the first live eval run exposed the
predicted per-stage-attribution tradeoff actually happening.** Original prompt made
sign_off depend on all three drafts, including whether the routing shortlist's keyword
match looked strong. In the first full run, 4 of 11 system abstains had the verifier
say, in its own words, that service_line and complexity were sound but the routing
shortlist was weak, and abstain the whole decision anyway - discarding two correct
answers because of a third field that was never going to be acted on autonomously in
the first place (a human always confirms the specific lead regardless of shortlist
confidence). Fixed by removing routing-shortlist quality from the sign-off criteria
entirely; it may still appear in the verifier's `reason` text but can no longer flip
`sign_off` or set `abstain_trigger`. This also fixed the "routing implies ERP work the
text never mentions" cross-stage-inconsistency example from the original entry above -
on inspection that scenario cannot actually occur, since the routing shortlist is
mechanically generated from whatever service_line the model just proposed, so it can
never disagree with it. Rejected: leaving the gate in place and just documenting it as
a limitation - the first live run showed it was not a rare edge case (4 of 27 gradeable
records, ~15%), so it was worth fixing before treating any accuracy number as final.

**2026-09-08 - Corrected the complexity prompt's "don't trust the client's framing"
guidance after the first live eval run showed a one-directional bias.** Every
complexity miss in the first full run (8 of 8) was the model rating HIGHER than golden,
never lower - a systematic tendency to call things complex, not a random spread of
errors. Root cause: the original prompt spent real estate warning the model not to be
fooled by a client's stated "simple" framing (written with ENQ-0037 specifically in
mind), and the model generalized that warning to be suspicious of every enquiry, not
just the ones where the client's own stated context actually contradicted their framing.
Rewrote the guidance to say the reverse as the default: most enquiries are what they
look like, and stated scope should only be overridden when something specific in the
client's own words contradicts it, not merely because a request is short or uses the
word "simple". Named calling a genuinely bounded request "complex" as a real cost (it
wastes a lead's time sizing a discovery engagement for a five-minute call), so the
prompt is not just "trust the client" but "match the estimate to the actual evidence in
either direction."

**2026-09-08 - Found real run-to-run variance in the live eval, most visibly on the
verifier's abstain decision for the hardest record.** Ran the identical pipeline twice
after the prompt fixes above. `ENQ-0036` (the new "genuine coin-flip, should abstain"
record) correctly abstained on one run and confidently answered "Technology & Data" on
the other, from the exact same input. Headline numbers also moved between the two runs
(service_line 92% -> 88%, complexity 71% -> 75%, routing top-1 83% -> 79%) purely from
API sampling variance, no code changes between them. Not treating either run's numbers
as ground truth; reporting the range instead. This is the concrete, observed version of
a risk named only in the abstract in the self-reported-confidence discussion earlier:
a single verifier call is one sample from a distribution, and on genuinely borderline
cases that distribution has real spread. The self-consistency ensemble option rejected
earlier (run N times, abstain on disagreement) is the direct fix for exactly this
failure mode - not pursued now because 31 golden records is too small a set to justify
tuning further against, and because the variance itself is useful, honest information
for the panel rather than something to paper over with a bigger prompt-engineering pass.

**2026-09-08 - Model choice: use the strongest available model for every call.**
At ~2,600 calls/year the price difference between model tiers is noise. Accuracy on the
subtle traps the golden set is built to catch (vocabulary-discipline cases like
ENQ-0011/ENQ-0014) is what the eval is actually testing, so optimise for that rather
than for per-call cost.

---

## Data

**2026-09-08 - Two separate files, deliberately.**
`data/enquiries.jsonl` = unlabelled input the system runs on (~200 records, realistic
distribution). `evals/golden.jsonl` = hand-labelled records, the answer key, never
fed to the classifier. Conflating them is the common failure; headline demo runs on the
former, all accuracy claims come from the latter.

**2026-09-08 - Golden set hand-labelled, not model-generated.**
Mix of clear / ambiguous / underspecified / abstain, each with a written rationale,
because writing the rationale is how the analyst's implicit judgment gets surfaced at
all. Rejected: generating labels with a model, which would make the eval measure
agreement with a model rather than correctness.

**2026-09-08 - Company profiles sourced from real PE portfolios, names fictionalised.**
Real portfolio companies (Thoma Bravo, Valor) used as source material for realistic
industry/size/business-model variety; names changed because attributing invented
operational dysfunction to named real companies is inappropriate in a submitted
artifact.

**2026-09-08 - Synthetic enquiries generated from templates, not an LLM.**
If the same model writes and classifies the enquiries, measured accuracy is inflated by
shared phrasing priors. Templates produce cruder text but the limitation is visible.
Seeded for reproducibility.

**2026-09-08 - Corpus distribution is realistic, not balanced.**
~56% clear, 16% ambiguous, 13% underspecified, 13% out-of-scope, 2% junk, plus ~4%
near-duplicate resubmissions. Out-of-scope tail (vendor pitches, job applicants,
existing-client support, legal-opinion requests) exists so the abstain path is exercised
on the demo run, not only in the eval.

**2026-09-08 - `_gen` archetype block is provenance, not ground truth.**
Recorded for generator debugging and demo stratification only. Scoring against it would
be circular: for ambiguous and underspecified archetypes the correct routing is
contested, which no generator can encode.

**2026-09-08 - Enrichment scoped to prior-client lookup and dedup.**
Brief says "enriches" without specifying. Highest-value additions at this scale are
whether the enquirer is an existing/prior client, and deduplication of repeat
submissions. Both are cheap; neither is mentioned in the brief.

**2026-09-08 - Reviewed the existing corpus and golden set before writing any triage
code, and added to the golden set rather than reworking the generator.** The generator
and golden set already covered: multi-service-line enquiries, vague one-liners
(including post-noise-pipeline mid-sentence truncation), out-of-scope traffic, and
three structurally distinct abstain triggers (jurisdictional legal-opinion overreach,
export-control/national-security, and an ethics line - "we could build this vs. we
should"). One real gap, self-identified in this log before the review: nearly every
ambiguous golden record resolves via the same move - two internal parties disagree,
sequence by which claim is testable. Closed it with two new freehand golden records
whose ambiguity comes from a different source: a genuine dual-fit between two service
lines with no gating question to sequence them, and a mismatch between the client's
stated (simple) framing and the true complexity implied by their own stated context.
Rejected: a broader rework of the 15 archetypes - the existing set already clears the
bar the brief sets; only the one identified bias was worth the time before code.

**2026-09-08 - Disclosure on the two added golden records (ENQ-0036, ENQ-0037): drafted
with the AI assistant, reviewed and approved by me - and yes, that is in tension with
the "not model-generated" rule above.** The distinction I am relying on: the rejected
practice was asking a model to LABEL existing enquiries, which makes the eval measure
agreement with the model rather than correctness. These two records were instead
authored adversarially - designed specifically to catch failure modes the classifier
was suspected of having - with the labels set by design intent, not by asking a model
what it thinks the answer is. The empirical check that the shared-phrasing-prior worry
did not materialise: the classifier (same model family as the author) FAILED both
records on multiple live runs - ENQ-0036 got a confident wrong answer instead of
abstaining on one run of two, and ENQ-0037 was misclassified as Strategy & Advisory on
every run. If shared priors were inflating agreement, the model would pass the cases it
wrote. It did not.

**2026-09-08 - Fixed a real bug found while adding to the golden set: ENQ-0007 was
pretty-printed across 20 physical lines, breaking one-record-per-line JSONL parsing.**
Reformatted to a single line, matching every other record; content unchanged. Caught
before it caused a silent partial read rather than after.

**2026-09-08 - Fixed a second bug: `.gitignore` had a blanket `data/` directory rule
and a blanket `*.jsonl` rule (leftover generic ML-project boilerplate), which would
have silently excluded `data/generate.py` (source) and `evals/golden.jsonl`
(hand-labelled ground truth) from git entirely.** Replaced with precise ignores for
just the two files that should not be tracked - `data/enquiries.jsonl` (reproducible
from a fixed seed) and `data/decisions.jsonl` (a runtime log, not source). The working
agreement's "git history is evidence of reasoning" doesn't hold if the actual answer
key was never committable in the first place.

---

## Evaluation

**2026-09-08 - Routing is scored as top-1 match and shortlist recall, not a single
accuracy number.** Follows directly from routing outputting a shortlist rather than one
name (see Modelling). Top-1 = does the highest-ranked candidate equal golden's
`route_to`; shortlist recall = is the correct lead anywhere in the 1-2 candidates
returned. Reported alongside service_line accuracy (primary exact match, secondary
tracked as a separate bonus stat) and abstain precision/recall against the golden
abstain records. Rejected: a single blended routing score - it would hide whether
misses are "wrong specialist entirely" or "right specialist, ranked second," which are
different failure modes with different fixes.

---

## Known limitations

**One verifier call reviews the whole decision, not each stage independently.** Catches
cross-stage inconsistency at the cost of per-stage attribution - see Modelling above.

**Routing rules are keyword-based and will not anticipate every phrasing.** Mitigated,
not solved, by the human always confirming rather than the system ever assigning alone.

**Golden set has a structural bias, partially addressed.** Most ambiguous entries still
resolve via the same move (two internal parties disagree, sequence by testability); two
new records test a different kind of ambiguity, but this is two records against many -
worth continuing to diversify past this prototype.

**Templated corpus is more uniform than real submissions.** A classifier can partly key
on sentence structure rather than meaning. The golden set is the guard - written
freehand, no shared template skeleton. A large gap between accuracy on `enquiries.jsonl`
and on `golden.jsonl` is that overfitting surfacing, and should be reported, not hidden.

**Routing labels assume all leads have capacity.** Real routing depends on current load
and availability, which a static golden set cannot encode. This is the seam where
classification stops and org state begins - and is the direct reason routing was
designed to always end in human confirmation rather than autonomous assignment.

**Silent failure is the primary production risk.** A misroute throws no error; it sits in
the wrong queue. The correction signal - a team lead reassigning or bouncing an enquiry
- is free ground truth, but only if instrumented from day one. The `TriageDecision`
schema reserves a `correction` field for this now, even though the reassignment step
itself is out of scope for this prototype.

**Human fallback atrophies.** If the analyst stops triaging entirely, in six months
nobody can catch errors and the tacit knowledge is gone. Argues for sampled human review
at a defined rate rather than full handover.

---

## Time

Budget: 2-3 hours as instructed.
Planned: ~30 min data, ~60 min core logic, ~30 min eval, ~30 min write-up, ~20 min
README/cleanup. Actuals to be recorded here; if the box is blown, note it rather than
hide it.
