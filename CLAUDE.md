# AIVC take-home: intake triage agent

## What this is
A 2-3 hour take-home. The deliverable is a working prototype of
classification/routing logic, plus a half-page write-up. It will be
defended in a 30-45 minute technical panel where the interviewers
interrogate trade-offs. Full brief: docs/brief.md — read it before
proposing anything.

## Scale — this governs every decision
40-60 enquiries per WEEK. ~2,600/year. One LLM call per enquiry costs
single-digit dollars per year. Latency and throughput are non-issues.

Anything justified only at 100x this volume is wrong here and reads as
a judgment failure. Do NOT introduce, unless I explicitly ask:
- vector DBs, embeddings, RAG
- fine-tuning or any training pipeline
- message queues, workers, async orchestration
- Docker, k8s, cloud infra, IaC
- a database (jsonl/sqlite is enough at this scale)
- web frameworks or a served API
- retry/backoff middleware, circuit breakers, caching layers

If you think one is genuinely needed, say so and name the volume
threshold at which it becomes justified — don't just add it.

Target: a single well-reasoned module plus an eval script, runnable
with `python`. Boring and legible beats impressive.

## Design commitments (mine — challenge them, don't silently change them)
- The three outputs are separate problems with different amounts of
  available ground truth. Service line: closed-set, recoverable from
  text. Complexity: subjective, no ground truth, where the analyst's
  tacit knowledge lives. Routing: depends on org state (lead capacity,
  prior client relationship) that the form does not contain. Do not
  collapse these into one prompt call.
- Routing is partly rules + capacity, not pure classification.
- The system must be able to ABSTAIN. Low confidence means it declines
  and hands to a human, rather than guessing.
- Every decision must be logged with enough structure that a downstream
  human reassignment can later be joined back to it as a label. Silent
  misroutes are the primary failure mode; capturing the correction
  signal is the point.

## Working agreement
- Plan before code. Show me the plan; wait for my go-ahead.
- Surface decisions to me rather than resolving them. When you hit a
  fork with real trade-offs, stop and present the options with your
  recommendation. I have to defend these choices live.
- After each meaningful decision, append 3 lines to docs/DECISIONS.md:
  what was chosen, what was rejected, why.
- Small commits with real messages. The git history is evidence of
  reasoning.
- No speculative generality. No abstractions with one implementation.
- If I ask for something that contradicts the scale rules above, push
  back before doing it.