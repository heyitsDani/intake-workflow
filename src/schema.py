"""
schema.py - data models for the intake triage pipeline.

Three separate problems get three separate result types (see
docs/DECISIONS.md, "Treated the three outputs as separate problems"), plus a
verifier result and the TriageDecision envelope that ties them together for
logging.

ServiceLine, ComplexityLevel and LeadId are closed sets fixed by the firm's
current service-line taxonomy and lead roster (see src/leads.py). Widening
either is an org change, not a code change - update the Literal and the
roster table together.

Every field on TriageDecision is populated even when the verifier does not
sign off. An abstained decision is still the system's best-effort draft, just
one flagged as unreliable - the human decides how much of it to trust, rather
than being handed an empty form.
"""

from __future__ import annotations

import datetime as dt
from typing import Literal, Optional
from uuid import uuid4

from pydantic import BaseModel, Field

ServiceLine = Literal[
    "Technology & Data",
    "Risk & Compliance",
    "Strategy & Advisory",
    "Finance & Transactions",
    "People & Change",
]

ComplexityLevel = Literal["simple", "moderate", "complex"]

LeadId = Literal[
    "lead_dpatel",
    "lead_okonkwo",
    "lead_novak",
    "lead_chaudhry",
    "lead_bergman",
    "lead_reyes",
    "lead_whitfield",
    "lead_amari",
]

AbstainTrigger = Literal["low_confidence", "above_authority"]


class EnquiryForm(BaseModel):
    description: str
    industry: str
    company_size: str
    urgency: Literal["Low", "Medium", "High"]


class Enquiry(BaseModel):
    """An inbound web-form submission, as read from data/enquiries.jsonl or
    evals/golden.jsonl."""

    id: str
    submitted_at: dt.datetime
    form: EnquiryForm


class ServiceLineResult(BaseModel):
    """Stage 1: closed-set classification, recoverable from text alone."""

    primary: ServiceLine
    secondary: Optional[ServiceLine] = None
    rationale: str


class ComplexityResult(BaseModel):
    """Stage 2: a subjective judgment call. No ground truth exists beyond the
    analyst's tacit sense of what a lead can size on one call versus what
    needs discovery first - see docs/DECISIONS.md."""

    value: ComplexityLevel
    rationale: str


class RoutingCandidate(BaseModel):
    """One candidate lead in the routing shortlist, with the specialty
    signal that put them there."""

    lead_id: LeadId
    rationale: str


class RoutingResult(BaseModel):
    """Stage 3: NOT a model call. A deterministic lookup (src/leads.py)
    against the service line and specialty keywords in the text. Always a
    shortlist, never a single forced answer - capacity and prior
    relationship never appear on the form, so the system's job is a good
    shortlist for a human to pick from, not a verdict. See
    docs/DECISIONS.md."""

    candidates: list[RoutingCandidate] = Field(min_length=1, max_length=2)


class VerifierResult(BaseModel):
    """Stage 4: reviews the whole assembled draft (all three stages above)
    against the original enquiry text and decides whether a human should
    see this as a starting point or take the enquiry from scratch.
    Implements both named abstain triggers in one place - see
    docs/DECISIONS.md."""

    sign_off: bool
    reason: str
    abstain_trigger: Optional[AbstainTrigger] = None


class Correction(BaseModel):
    """Populated later, outside this prototype, when a team lead reassigns
    or bounces an enquiry. Reserved now so that loop has somewhere to write
    without a schema migration - see docs/DECISIONS.md ("Silent failure is
    the primary production risk")."""

    corrected_field: Literal["service_line", "complexity", "routing"]
    corrected_value: str
    corrected_by: str
    corrected_at: dt.datetime


class TriageDecision(BaseModel):
    """The full record of one triage run, logged whole via src/logging.py.
    Enough structure that a downstream human reassignment can be joined
    back to it as a label - see CLAUDE.md."""

    decision_id: str = Field(default_factory=lambda: f"DEC-{uuid4().hex[:10]}")
    enquiry_id: str
    submitted_at: dt.datetime
    service_line: ServiceLineResult
    complexity: ComplexityResult
    routing: RoutingResult
    verifier: VerifierResult
    abstain: bool
    correction: Optional[Correction] = None
