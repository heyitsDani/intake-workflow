# Intake Triage Agent - Write-up

**What breaks first in production:** silent misrouting. Nothing in this
system raises an error when it routes wrong - a misclassified enquiry sits
in the wrong lead's queue until someone downstream notices, which may be
days later or never. The routing shortlist is also brittle to phrasing
outside its keyword table: it degrades to an uninformative full-line
shortlist rather than a confident wrong answer, which is a safer failure
mode, but a stale roster (a lead leaves, a specialty shifts) will silently
produce a worse shortlist with no signal that it happened. Third: both the
demo corpus and the eval's own generator are templated text, and the golden
set is hand-written specifically as a guard against overfitting to that
template's sentence structure - a large gap between accuracy on
`data/enquiries.jsonl` and on `evals/golden.jsonl` would be the first real
warning sign of that, and nothing currently automates the comparison.

**What to monitor:**
- Abstain rate over time, split by trigger (`low_confidence` vs
  `above_authority`). A sudden drop usually means the verifier has become
  overconfident, not that enquiries got easier.
- The verifier's sign-off rate against actual human overrides, once the
  correction loop below exists - this is the real calibration check, and it
  does not exist yet.
- Routing shortlist recall specifically, tracked apart from service-line and
  complexity accuracy, since it degrades independently and for a different
  reason (a stale keyword table vs. a genuinely hard case).
- Drift between the corpus's assumed distribution (mostly clear, with a
  small ambiguous/underspecified/out-of-scope tail) and what actually
  arrives - a shift toward more ambiguous or out-of-scope traffic changes
  what an acceptable abstain rate even looks like.

**Fallback when the model gets it wrong:**
- Service line and complexity are gated by the verifier. Below sign-off, the
  enquiry goes to a human with the draft still visible and clearly marked
  unreliable, not blank - the system's best guess is worth showing even when
  it should not be trusted outright.
- Routing is never autonomous, by design, regardless of how confident the
  earlier stages were: the system always hands a human a shortlist of 1-2
  candidate leads with rationale, and the human makes the final call. This
  is the one stage where the fallback is the default behaviour, because
  capacity and prior-relationship state never appear on the form and no
  model can be trusted to guess them.
- The `TriageDecision` schema reserves a `correction` field so a human
  reassignment can be logged back against the original decision. That
  correction signal is the actual ground truth a real deployment needs, and
  wiring it up is the single most important next step, ahead of any
  accuracy improvement to the pipeline itself.

Full reasoning and every rejected alternative: `docs/DECISIONS.md`.
