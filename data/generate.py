"""
generate.py -- synthetic inbound enquiry generator for the intake triage prototype.

Writes data/enquiries.jsonl: unlabelled web-form submissions in the shape the
triage system consumes in production.

THIS IS NOT THE EVAL SET.
    data/enquiries.jsonl   unlabelled input, what the system runs on
    evals/golden.jsonl     hand-labelled answer key, what the system is scored on

Every record carries a `_gen` block recording which archetype produced it. That is
provenance for debugging the generator, not ground truth. Scoring against `_gen`
would be circular -- the generator's intent and the correct triage decision are not
the same thing, and for the ambiguous and underspecified archetypes the whole point
is that the right answer is contested. Score against evals/golden.jsonl only.

Design notes (see docs/DECISIONS.md):
  - Templated rather than LLM-generated. If the same model that writes the enquiries
    also classifies them, measured accuracy is inflated by shared phrasing priors.
    Templates are cruder but the failure mode is honest and visible.
  - Seeded, so the corpus is reproducible and the eval is stable across runs.
  - Distribution mirrors real intake, not a balanced eval set: mostly easy, with a
    realistic tail of vague, out-of-scope, and junk submissions.

Usage:
    python data/generate.py                       # 200 records, seed 7
    python data/generate.py -n 600 --seed 42
    python data/generate.py -o /tmp/sample.jsonl
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import random
from pathlib import Path

# --------------------------------------------------------------------------
# Shared vocabulary. Kept in sync with the taxonomy in evals/golden.jsonl.
# --------------------------------------------------------------------------

COMPANY_SIZES = ["1-50", "50-250", "250-500", "500-1000", "1000-5000", "5000+"]
SIZE_WEIGHTS = [12, 28, 24, 16, 14, 6]

URGENCY = ["Low", "Medium", "High"]
URGENCY_WEIGHTS = [22, 52, 26]

INDUSTRIES = [
    "Software & Technology", "Enterprise Software", "Cybersecurity", "Fintech",
    "Insurance & Financial Services", "Healthcare Services", "Biotechnology",
    "Manufacturing", "Industrial Robotics", "Logistics & Delivery",
    "Consumer Retail", "D2C Consumer", "Food & Beverage", "EdTech",
    "Energy & Utilities", "Professional Services", "Media & Entertainment",
    "Real Estate", "Transportation", "Advanced Manufacturing",
]

# --------------------------------------------------------------------------
# Archetypes. Each composes a description from context + pain + ask + constraint.
# `bucket` records what kind of triage case the archetype is meant to produce.
# --------------------------------------------------------------------------

ARCHETYPES = {
    # ---------------- clear cases: scope already drawn by the client ----------
    "clear_build": {
        "bucket": "clear",
        "weight": 20,
        "context": [
            "We run a subscription business and have order and usage data going back several years.",
            "We operate a platform connecting buyers and suppliers across a few thousand accounts.",
            "We manage a fleet of connected devices deployed at customer sites.",
            "We sell a SaaS product and log detailed feature usage events already.",
        ],
        "pain": [
            "Right now this analysis is done manually in a spreadsheet by one person, updated weekly.",
            "Our team does this on a sample basis and we want it running across every account.",
            "We have the data but nobody has built anything on top of it.",
        ],
        "ask": [
            "We want someone to build the model and a simple dashboard our ops team can work from.",
            "Looking for someone to build and validate this against our historical data.",
            "We need the matching and flagging logic built and wired into our existing alerting.",
        ],
        "constraint": [
            "We can handle integration ourselves, we just need the model. Would like results within 6 weeks.",
            "Not looking for a full platform, just a working first version within a month.",
            "We want to see whether this is useful before doing anything more elaborate.",
        ],
    },
    "clear_assess": {
        "bucket": "clear",
        "weight": 12,
        "context": [
            "Several of our larger customers have made independent third-party assessment a condition of renewal.",
            "We are pursuing certification because institutional clients require it before onboarding.",
            "Our regulatory affairs lead expects examiners to ask for documented governance this year.",
        ],
        "pain": [
            "We have never had an outside party review our controls.",
            "Our internal documentation has grown organically and nobody has checked it against the standard.",
        ],
        "ask": [
            "We need an independent readiness assessment and a written gap report.",
            "We want a scoped review and a remediation roadmap we can share under NDA.",
        ],
        "constraint": [
            "Our internal team will handle remediation, we need the assessment only. Budget is approved.",
            "Scope is one product line, not the whole platform. We need this in hand by end of quarter.",
        ],
    },
    "clear_process": {
        "bucket": "clear",
        "weight": 10,
        "context": [
            "We are expanding into two new verticals this year.",
            "We are projecting roughly three times our current volume over the next two quarters.",
            "We are opening a second facility and expect the current process to strain.",
        ],
        "pain": [
            "Our onboarding process is manual and works fine today but will not hold at higher volume.",
            "Our intake and handoff steps were designed when we were a third of this size.",
        ],
        "ask": [
            "Looking for someone to map the current process, find where it breaks at scale, and help redesign it.",
            "We want the process right before we automate anything.",
        ],
        "constraint": [
            "Not looking for new software at this stage. No hard deadline, but we would like to start within a month.",
            "We would rather fix the workflow than buy a tool. Flexible on timing.",
        ],
    },
    "clear_finance": {
        "bucket": "clear",
        "weight": 8,
        "context": [
            "We have had an inbound acquisition approach and the board wants to be prepared.",
            "We are heading into a fundraising conversation next quarter.",
            "We are scaling our financing programme and want to check our assumptions first.",
        ],
        "pain": [
            "Our own numbers have never been pressure-tested by anyone outside the company.",
            "Underwriting has been inconsistent across regions and nobody has reconciled it.",
        ],
        "ask": [
            "We want an independent financial and operational diligence review before we go further.",
            "We need a cleaner unit economics model and a review of our default risk assumptions.",
        ],
        "constraint": [
            "This is confidential and time-sensitive. We need a report to the board within three weeks.",
            "We have two years of performance data. Ideally done within four to five weeks.",
        ],
    },
    "clear_people": {
        "bucket": "clear",
        "weight": 7,
        "context": [
            "Our team has grown from a handful of people to several dozen in under two years.",
            "We are doubling headcount this year across two offices.",
        ],
        "pain": [
            "We have no consistent onboarding and new hires learn by shadowing whoever is free.",
            "Quality varies a lot between people and we have never written down what good looks like.",
        ],
        "ask": [
            "We want help building a proper onboarding curriculum and a calibration process.",
            "Looking for someone to design the training programme and help us roll it out.",
        ],
        "constraint": [
            "We would like something in place before the next hiring wave in the autumn.",
            "Our own team can run it once it exists, we need help designing it.",
        ],
    },
    # ---------------- ambiguous: real judgment required -----------------------
    "ambiguous_two_theories": {
        "bucket": "ambiguous",
        "weight": 8,
        "context": [
            "Our churn has been climbing for two quarters and we do not agree internally on why.",
            "Margins have been eroding and two teams have different explanations.",
            "Support volume is up sharply and nobody agrees on the cause.",
        ],
        "pain": [
            "One team thinks it is a product issue, another thinks the data is being miscategorised.",
            "Operations blames a technical defect, finance thinks the numbers are simply wrong.",
        ],
        "ask": [
            "We need this resolved by someone outside the argument.",
            "We want help working out which explanation actually holds before we act on either.",
        ],
        "constraint": [
            "This is costing us real revenue every month it goes unresolved.",
            "We need an answer before our next investor update.",
        ],
    },
    "ambiguous_compound": {
        "bucket": "ambiguous",
        "weight": 7,
        "context": [
            "Leadership wants to explore a new line of business under our existing brand.",
            "We are considering expanding into an adjacent service our customers keep asking for.",
        ],
        "pain": [
            "Separately, we have internal pressure to formalise something that has been ad hoc for years.",
            "At the same time our own internal processes for this are undocumented.",
        ],
        "ask": [
            "Not sure if these are the same project or two different ones. Would like to talk through both.",
            "We would like help working out where to start and whether these are related.",
        ],
        "constraint": [
            "No firm deadline, this is exploratory for now.",
            "We would like a point of view before the next planning cycle.",
        ],
    },
    "ambiguous_failed_prior": {
        "bucket": "ambiguous",
        "weight": 6,
        "context": [
            "We tried something similar about eighteen months ago and it did not stick.",
            "We brought in a firm for this last year and everyone liked the workshops and nothing changed.",
        ],
        "pain": [
            "The model was built, handed over, and nobody trusted the output enough to use it.",
            "My read is the incentives were never changed, so the new process was ignored.",
        ],
        "ask": [
            "We do not want to repeat that. Looking for someone who will address why it failed.",
            "We want help figuring out whether the problem was the tool or something underneath it.",
        ],
        "constraint": [
            "Leadership wants this resolved before the next planning cycle.",
            "We have budget but limited patience for another round of the same thing.",
        ],
    },
    # ---------------- underspecified: needs a call before routing -------------
    "underspecified": {
        "bucket": "underspecified",
        "weight": 9,
        "context": [
            "We have a few people spending most of their week on approvals paperwork.",
            "Corporate keeps asking why our facility-level data does not roll up to anything they can see.",
            "Growth has flattened in our most mature markets and leadership has a lot of theories.",
            "Someone suggested we look at whether any of this can be handled better.",
        ],
        "pain": [
            "We do not know if we need a technical fix, a process fix, or a bigger conversation.",
            "Different people here are asking for different things and none of them have compared notes.",
            "Honestly not sure what kind of engagement this even is.",
        ],
        "ask": [
            "Would like to get some outside eyes on this.",
            "Open to a conversation to work out what we actually need.",
        ],
        "constraint": [
            "Would like to move on this soon.",
            "Board meeting is in a few weeks and we want a point of view before then.",
            "",
        ],
    },
    # ---------------- out of scope: should not enter the routing path ---------
    "oos_vendor_pitch": {
        "bucket": "out_of_scope",
        "weight": 4,
        "context": [
            "Hi, I lead partnerships at a workflow automation platform and I think there is a strong fit here.",
            "Reaching out because our AI documentation tool is used by several firms like yours.",
        ],
        "pain": [""],
        "ask": [
            "Would love 15 minutes with whoever owns tooling decisions to walk through a demo.",
            "Happy to send over a deck and set up a call with your team.",
        ],
        "constraint": [
            "We are running a promotion for new partners this quarter.",
            "",
        ],
    },
    "oos_jobseeker": {
        "bucket": "out_of_scope",
        "weight": 3,
        "context": [
            "I could not find a careers page so I am using this form.",
            "Hello, I am a recent graduate in economics and data analytics.",
        ],
        "pain": [""],
        "ask": [
            "I would like to apply for any analyst openings you may have.",
            "Attaching my CV, please pass it to whoever handles recruiting.",
        ],
        "constraint": [
            "Available to start immediately.",
            "",
        ],
    },
    "oos_existing_client": {
        "bucket": "out_of_scope",
        "weight": 3,
        "context": [
            "We are already working with your team on the reporting project.",
            "This is regarding our current engagement, not a new request.",
        ],
        "pain": [
            "We have not had a status update in two weeks and our internal deadline is Friday.",
            "There is an invoice discrepancy we raised last month that is still open.",
        ],
        "ask": [
            "Can someone from that team get back to us.",
            "Please route this to whoever is managing our account.",
        ],
        "constraint": ["", ""],
    },
    "oos_legal_opinion": {
        "bucket": "out_of_scope",
        "weight": 2,
        "context": [
            "Our legal team wants a second read on how we structure a specific transaction.",
            "We are in live negotiations and want help with the regulatory classification.",
        ],
        "pain": [
            "Outside counsel has weighed in but we want another opinion before we proceed.",
        ],
        "ask": [
            "We need help structuring this so it falls outside the relevant jurisdiction.",
            "Looking for someone to pressure-test the specific structure before we sign.",
        ],
        "constraint": [
            "This needs to be addressed within the next few weeks.",
        ],
    },
    # ---------------- junk ----------------------------------------------------
    "junk": {
        "bucket": "junk",
        "weight": 2,
        "context": ["test", "asdf", "Hello", "n/a", "please call me"],
        "pain": [""],
        "ask": ["", ""],
        "constraint": ["", ""],
    },
}

# --------------------------------------------------------------------------
# Noise. Real form submissions are not clean prose.
# --------------------------------------------------------------------------

TYPO_SWAPS = [
    ("the ", "teh "), ("and ", "adn "), ("our ", "or "), ("we ", "we  "),
    ("management", "managment"), ("separately", "seperately"),
]


def strip_caps(text: str) -> str:
    return text.lower()


def strip_punct(text: str) -> str:
    return text.replace(".", "").replace(",", "")


def add_typos(text: str, rng: random.Random) -> str:
    for _ in range(rng.randint(1, 2)):
        old, new = rng.choice(TYPO_SWAPS)
        if old in text:
            text = text.replace(old, new, 1)
    return text


def as_pasted_email(text: str, rng: random.Random) -> str:
    header = rng.choice([
        "FW: intro call\n\n---------- Forwarded message ----------\n",
        "see below, forwarding what our COO sent me\n\n>>> ",
    ])
    return header + text


def truncate_hard(text: str, rng: random.Random) -> str:
    words = text.split()
    return " ".join(words[: rng.randint(6, 14)])


NOISE_FNS = [
    (strip_caps, 0.30),
    (strip_punct, 0.15),
    (add_typos, 0.20),
    (as_pasted_email, 0.10),
    (truncate_hard, 0.08),
]

# Junk and underspecified submissions are messier than considered ones.
NOISE_RATE_BY_BUCKET = {
    "clear": 0.18,
    "ambiguous": 0.20,
    "underspecified": 0.45,
    "out_of_scope": 0.35,
    "junk": 0.90,
}


def apply_noise(text: str, bucket: str, rng: random.Random) -> tuple[str, list[str]]:
    """Roughen the text. Returns (text, names of transforms applied)."""
    applied: list[str] = []
    if rng.random() > NOISE_RATE_BY_BUCKET.get(bucket, 0.2):
        return text, applied
    for fn, p in NOISE_FNS:
        if rng.random() < p:
            text = fn(text, rng) if fn in (add_typos, as_pasted_email, truncate_hard) else fn(text)
            applied.append(fn.__name__)
    return text, applied


# --------------------------------------------------------------------------
# Generation
# --------------------------------------------------------------------------

def compose(arch: dict, rng: random.Random) -> str:
    parts = [
        rng.choice(arch["context"]),
        rng.choice(arch["pain"]),
        rng.choice(arch["ask"]),
        rng.choice(arch["constraint"]),
    ]
    return " ".join(p for p in parts if p).strip()


def business_timestamp(start: dt.date, week: int, rng: random.Random) -> dt.datetime:
    day = start + dt.timedelta(weeks=week, days=rng.randint(0, 4))
    return dt.datetime.combine(
        day, dt.time(rng.randint(8, 17), rng.choice([0, 5, 12, 18, 23, 30, 41, 47, 55]))
    )


def build(n: int, seed: int, start: dt.date, per_week: tuple[int, int]) -> list[dict]:
    rng = random.Random(seed)
    keys = list(ARCHETYPES)
    weights = [ARCHETYPES[k]["weight"] for k in keys]

    records: list[dict] = []
    week = 0
    while len(records) < n:
        for _ in range(rng.randint(*per_week)):
            if len(records) >= n:
                break
            key = rng.choices(keys, weights=weights, k=1)[0]
            arch = ARCHETYPES[key]
            text = compose(arch, rng)
            text, noise = apply_noise(text, arch["bucket"], rng)
            records.append({
                "submitted_at": business_timestamp(start, week, rng),
                "form": {
                    "description": text,
                    "industry": rng.choice(INDUSTRIES),
                    "company_size": rng.choices(COMPANY_SIZES, weights=SIZE_WEIGHTS, k=1)[0],
                    "urgency": rng.choices(URGENCY, weights=URGENCY_WEIGHTS, k=1)[0],
                },
                "_gen": {"archetype": key, "bucket": arch["bucket"], "noise": noise},
            })
        week += 1

    # Repeat submissions: the same enquiry sent twice, hours or days apart.
    # Dedup is one of the cheapest wins in intake, so the corpus has to contain some.
    for _ in range(max(1, int(len(records) * 0.04))):
        original = rng.choice(records)
        dupe = json.loads(json.dumps(original, default=str))
        dupe["submitted_at"] = original["submitted_at"] + dt.timedelta(
            hours=rng.choice([2, 5, 26, 49])
        )
        if rng.random() < 0.5:  # resubmitted with a nudge on the front
            dupe["form"]["description"] = (
                "Following up as I did not hear back. " + dupe["form"]["description"]
            )
        dupe["_gen"]["duplicate_of_archetype"] = True
        records.append(dupe)

    records.sort(key=lambda r: str(r["submitted_at"]))
    for i, rec in enumerate(records, start=1):
        rec["id"] = f"ENQ-S{i:04d}"  # S for synthetic; golden set uses ENQ-00NN
        ts = rec["submitted_at"]
        rec["submitted_at"] = (
            ts.strftime("%Y-%m-%dT%H:%M:%SZ") if isinstance(ts, dt.datetime) else str(ts)
        )
        # id and submitted_at first, for readability
        rec_ordered = {k: rec[k] for k in ("id", "submitted_at", "form", "_gen")}
        records[i - 1] = rec_ordered
    return records


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("-n", type=int, default=200, help="number of records (default 200, ~4 weeks)")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("-o", "--out", default="data/enquiries.jsonl")
    ap.add_argument("--start", default="2026-01-05", help="first Monday, ISO date")
    args = ap.parse_args()

    records = build(
        n=args.n,
        seed=args.seed,
        start=dt.date.fromisoformat(args.start),
        per_week=(40, 60),  # matches the brief's stated intake volume
    )

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as fh:
        for rec in records:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")

    counts: dict[str, int] = {}
    for r in records:
        counts[r["_gen"]["bucket"]] = counts.get(r["_gen"]["bucket"], 0) + 1
    dupes = sum(1 for r in records if r["_gen"].get("duplicate_of_archetype"))

    print(f"wrote {len(records)} records to {out}")
    for bucket, count in sorted(counts.items(), key=lambda kv: -kv[1]):
        print(f"  {bucket:16s} {count:4d}  ({count / len(records):.0%})")
    print(f"  {'(near-duplicates)':16s} {dupes:4d}")


if __name__ == "__main__":
    main()