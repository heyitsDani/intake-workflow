"""
logging.py - decision persistence.

One function: append a finished TriageDecision to a JSONL file. No logging
framework, no database - see CLAUDE.md's scale rules and docs/DECISIONS.md.
Every decision is written whole, including the (initially empty) `correction`
field a future human-reassignment step would populate - see docs/DECISIONS.md
("Silent failure is the primary production risk").
"""

from __future__ import annotations

from pathlib import Path

from src.schema import TriageDecision

DEFAULT_DECISIONS_PATH = Path("data/decisions.jsonl")


def append_decision(decision: TriageDecision, path: Path = DEFAULT_DECISIONS_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(decision.model_dump_json() + "\n")
