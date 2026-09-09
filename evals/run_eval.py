"""
run_eval.py - score the triage pipeline against evals/golden.jsonl.

evals/golden.jsonl is the only source of truth used here. data/enquiries.jsonl
is never touched by this script - see data/generate.py's module docstring and
docs/DECISIONS.md ("Two separate files, deliberately").

Usage:
    python evals/run_eval.py
"""

from __future__ import annotations

import json
from pathlib import Path

from src.logging import append_decision
from src.schema import Enquiry, TriageDecision
from src.triage import triage

GOLDEN_PATH = Path("evals/golden.jsonl")
DECISIONS_PATH = Path("data/decisions.jsonl")


def load_golden(path: Path = GOLDEN_PATH) -> list[dict]:
    records = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def run_one(record: dict) -> tuple[TriageDecision | None, Exception | None]:
    enquiry = Enquiry.model_validate({
        "id": record["id"],
        "submitted_at": record["submitted_at"],
        "form": record["form"],
    })
    try:
        decision = triage(enquiry)
    except Exception as exc:  # batch script: log and continue, don't crash the run
        return None, exc
    append_decision(decision, DECISIONS_PATH)
    return decision, None


def score(records: list[dict], decisions: dict[str, TriageDecision]) -> dict:
    """Score everything that can be scored, and separately report what
    couldn't be. Service_line/complexity/routing are only graded on records
    where BOTH golden and the system committed to an answer - you cannot
    score "was the routing right" against a decision that abstained."""

    golden_abstain_ids: set[str] = set()
    system_abstain_ids: set[str] = set()
    golden_non_abstain = 0
    graded = 0
    service_line_hits = 0
    complexity_hits = 0
    routing_top1_hits = 0
    routing_shortlist_hits = 0
    secondary_present = 0
    secondary_hits = 0
    misses: list[tuple[dict, TriageDecision | None, str]] = []

    for record in records:
        rid = record["id"]
        labels = record["labels"]
        decision = decisions.get(rid)

        if labels["abstain"]:
            golden_abstain_ids.add(rid)
        else:
            golden_non_abstain += 1

        if decision is None:
            misses.append((record, None, "pipeline error"))
            continue

        if decision.abstain:
            system_abstain_ids.add(rid)

        if labels["abstain"] or decision.abstain:
            if labels["abstain"] != decision.abstain:
                misses.append((record, decision, "abstain mismatch"))
            continue

        graded += 1
        sl_hit = decision.service_line.primary == labels["service_line"]
        cx_hit = decision.complexity.value == labels["complexity"]
        candidate_ids = [c.lead_id for c in decision.routing.candidates]
        top1_hit = candidate_ids[0] == labels["route_to"]
        shortlist_hit = labels["route_to"] in candidate_ids

        service_line_hits += sl_hit
        complexity_hits += cx_hit
        routing_top1_hits += top1_hit
        routing_shortlist_hits += shortlist_hit

        if labels.get("secondary_service_line"):
            secondary_present += 1
            if labels["secondary_service_line"] in (decision.service_line.primary, decision.service_line.secondary):
                secondary_hits += 1

        if not (sl_hit and cx_hit and top1_hit):
            misses.append((record, decision, "field mismatch"))

    return {
        "total": len(records),
        "errored": sum(1 for _, d, kind in misses if kind == "pipeline error"),
        "golden_abstain_ids": golden_abstain_ids,
        "system_abstain_ids": system_abstain_ids,
        "graded": graded,
        "golden_non_abstain": golden_non_abstain,
        "service_line_acc": service_line_hits / graded if graded else float("nan"),
        "complexity_acc": complexity_hits / graded if graded else float("nan"),
        "routing_top1_acc": routing_top1_hits / graded if graded else float("nan"),
        "routing_shortlist_acc": routing_shortlist_hits / graded if graded else float("nan"),
        "secondary_present": secondary_present,
        "secondary_hits": secondary_hits,
        "misses": misses,
    }


def print_report(metrics: dict) -> None:
    golden_abstain = metrics["golden_abstain_ids"]
    system_abstain = metrics["system_abstain_ids"]
    overlap = len(golden_abstain & system_abstain)
    abstain_recall = overlap / len(golden_abstain) if golden_abstain else float("nan")
    abstain_precision = overlap / len(system_abstain) if system_abstain else float("nan")

    print(f"records:              {metrics['total']}")
    print(f"pipeline errors:      {metrics['errored']} (excluded from every metric below)")
    print(f"golden abstain cases: {len(golden_abstain)}")
    print(f"system abstained on:  {len(system_abstain)}")
    print(f"  abstain recall:     {abstain_recall:.0%}  (of golden abstains, how many the system also flagged)")
    print(f"  abstain precision:  {abstain_precision:.0%}  (of system abstains, how many were truly golden abstains)")
    print()
    print(f"graded (golden and system both committed to an answer): {metrics['graded']} / {metrics['golden_non_abstain']}")
    print(f"  service_line accuracy:    {metrics['service_line_acc']:.0%}")
    print(f"  complexity accuracy:      {metrics['complexity_acc']:.0%}")
    print(f"  routing top-1 accuracy:   {metrics['routing_top1_acc']:.0%}")
    print(f"  routing shortlist recall: {metrics['routing_shortlist_acc']:.0%}")
    if metrics["secondary_present"]:
        print(f"  secondary service line correctly surfaced: {metrics['secondary_hits']}/{metrics['secondary_present']}")
    print()
    print(f"misses ({len(metrics['misses'])}):")
    for record, decision, kind in metrics["misses"]:
        labels = record["labels"]
        print(f"\n--- {record['id']} ({kind}) ---")
        print(f"golden:  service_line={labels['service_line']!r} complexity={labels['complexity']!r} "
              f"route_to={labels['route_to']!r} abstain={labels['abstain']}")
        print(f"  golden rationale: {record['meta']['rationale'][:220]}...")
        if decision is None:
            print("system:  <pipeline error, see console output above for the exception>")
            continue
        candidate_ids = [c.lead_id for c in decision.routing.candidates]
        print(f"system:  service_line={decision.service_line.primary!r} complexity={decision.complexity.value!r} "
              f"routing_shortlist={candidate_ids} abstain={decision.abstain}")
        print(f"  system rationale: {decision.service_line.rationale[:220]}")
        if decision.abstain:
            print(f"  verifier: [{decision.verifier.abstain_trigger}] {decision.verifier.reason}")


def main() -> None:
    records = load_golden()
    decisions: dict[str, TriageDecision] = {}

    for i, record in enumerate(records, start=1):
        print(f"[{i}/{len(records)}] {record['id']}...", end=" ", flush=True)
        decision, error = run_one(record)
        if error is not None:
            print(f"ERROR: {error}")
        else:
            decisions[record["id"]] = decision
            print("abstained" if decision.abstain else "done")

    print()
    metrics = score(records, decisions)
    print_report(metrics)


if __name__ == "__main__":
    main()
