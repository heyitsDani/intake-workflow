## Repository Structure

intake-triage-agent/
├── CLAUDE.md              # standing context, auto-loaded every session
├── README.md              # this file
├── docs/
│   ├── brief.pdf
│   ├── brief.md
│   ├── ARCHITECTURE.md    # one diagram + notes: data flow, integration, day-one instrumentation
│   └── DECISIONS.md       # running decisions log - what was chosen, rejected, why
├── data/
│   ├── generate.py        # synthetic data generator
│   ├── enquiries.jsonl    # unlabelled synthetic input (never used for scoring)
│   └── decisions.jsonl    # every triage decision, written by evals/run_eval.py
├── src/
│   ├── schema.py          # pydantic models for the whole pipeline
│   ├── leads.py           # static lead roster + routing shortlist rules
│   ├── config.py          # API key / model config
│   ├── logging.py         # decision persistence (one function)
│   └── triage.py          # the pipeline: service_line, complexity, routing, verifier
├── evals/
│   ├── golden.jsonl       # hand-labelled answer key, 31 cases
│   └── run_eval.py
└── WRITEUP.md             # the half-page deliverable

## Setup

```
uv sync
```

Set your API key in `.env` (already gitignored):

```
ANTHROPIC_API_KEY=sk-ant-...
```

## Run

Regenerate the synthetic, unlabelled demo corpus:

```
python data/generate.py
```

Run the eval against the hand-labelled golden set:

```
python -m evals.run_eval
```

(Run as a module, not a script, so `src` resolves as a sibling package
without needing to fiddle with `PYTHONPATH`.)

This calls the Claude API three times per enquiry (service_line, complexity,
and a verifier that reviews the assembled decision and can abstain to a
human) - routing is a local rules lookup, not a call. It prints progress per
record, then a summary of service-line, complexity, routing, and abstain
accuracy, followed by every miss with the model's rationale next to the
hand-written one.

Every decision, including abstained ones, is appended to
`data/decisions.jsonl` - see `docs/DECISIONS.md` for why.

## Why it stops here

`CLAUDE.md` scopes this to ~40-60 enquiries/week. No vector store, no
fine-tuning, no queue, no served API, no database - see `docs/DECISIONS.md`
for the volume threshold at which each of those would become worth adding.
