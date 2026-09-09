# Intake Triage Agent - Write-up

**What breaks first in production:** silent misrouting. A wrong decision
raises no error - the enquiry just sits in the wrong lead's queue until a
person notices, days later or never. Second, the routing shortlist is
keyword-based, so a stale roster (a lead leaves, a specialty shifts)
degrades it silently: no error, just quietly worse shortlists. Third, and
most bluntly: this system has never seen a real enquiry. It was built and
measured entirely on synthetic data, so the first weeks of production are
the real eval. I would dual-run it alongside the analyst rather than
replace them, until the correction loop below has produced enough labels
to know the true error rate - the same reason docs/DECISIONS.md refuses
to claim improvement over an unmeasured baseline.

**What to monitor:**
- Abstain rate, split by trigger (`low_confidence` vs `above_authority`).
  A sudden drop usually means the verifier got overconfident, not that
  enquiries got easier.
- How often the analyst's final routing pick falls outside the system's
  shortlist. No ground-truth labels needed - the human's pick is the label.
- Human corrections to service line and complexity, joined back to the
  original decision via the correction field. This is the real calibration
  check on the verifier's sign-offs, and it does not exist until that loop
  is wired.
- Distribution drift: the share of clear vs ambiguous vs out-of-scope
  traffic in the decision log. A shift changes what a healthy abstain rate
  even looks like.
- Decision stability on near-duplicate resubmissions. Live testing showed
  real run-to-run variance on borderline cases (evals/RESULTS.md): the
  same enquiry can abstain one run and get a confident answer the next.
  Duplicates arriving days apart are a free consistency probe.

**Fallback when the model gets it wrong:**
- Service line and complexity are gated by a verifier call. Below
  sign-off, the enquiry goes to a human with the draft still visible and
  clearly marked unreliable, not blank - the best guess is worth showing
  even when it should not be trusted outright.
- Routing is never autonomous, by design, regardless of confidence: the
  system always hands a human a 1-2 lead shortlist with rationale, and the
  human makes the final call, because capacity and prior-relationship
  state never appear on the form and no model should guess them.
- Every decision is logged whole to `decisions.jsonl` with a reserved
  `correction` field, so a team lead's reassignment becomes a free
  training label joined to the original decision. Wiring that loop is the
  single most important next step, ahead of any accuracy work.

Measured results: `evals/RESULTS.md`. Full reasoning and every rejected
alternative: `docs/DECISIONS.md`.
