"""
leads.py - the static lead roster and routing shortlist logic.

Not a model call. See docs/DECISIONS.md ("Routing is rules, not a model
call, and structurally never autonomous"). Specialty keyword lists were
built from the distinctions already articulated in evals/golden.jsonl's
hand-written rationale (e.g. ENQ-0007: "Patel has the ERP background,
Okonkwo's practice is analytics").

This table is an org chart fact, not a judgment call - update it directly
when the roster changes. It will not anticipate every phrasing (see
docs/DECISIONS.md known limitations); that brittleness is why routing
always ends in human confirmation rather than autonomous assignment.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.schema import LeadId, RoutingCandidate, RoutingResult, ServiceLine


@dataclass(frozen=True)
class Lead:
    lead_id: LeadId
    name: str
    service_line: ServiceLine
    specialties: str  # short human-readable description, doubles as candidate rationale
    keywords: tuple[str, ...]  # lowercase signal words, drawn from real enquiry text


ROSTER: tuple[Lead, ...] = (
    Lead(
        "lead_dpatel", "Patel", "Technology & Data",
        "ERP, systems integration, legacy/vendor-master data remediation",
        ("erp", "vendor master", "integration", "legacy system", "migrat",
         "purchase order", "procurement"),
    ),
    Lead(
        "lead_okonkwo", "Okonkwo", "Technology & Data",
        "Analytics, ML, predictive modeling, detection/flagging builds",
        ("predict", "model", "analytics", "dashboard", "forecast", "churn",
         "machine learning", " ml ", "algorithm", "scor"),
    ),
    Lead(
        "lead_novak", "Novak", "Risk & Compliance",
        "Security audits, penetration testing, SOC 2 / security certification readiness",
        ("security", "penetration test", "soc 2", "soc2", "cyber", "vulnerabilit"),
    ),
    Lead(
        "lead_chaudhry", "Chaudhry", "Risk & Compliance",
        "Regulated-industry examination readiness, model governance, physical/industrial safety",
        ("regulat", "examin", "governance", "licens", "safety", "inspection",
         "fda", "compliance framework"),
    ),
    Lead(
        "lead_bergman", "Bergman", "Strategy & Advisory",
        "Operating model design, process redesign, org/GTM structure",
        ("process", "operating model", "workflow", "org design", "go-to-market",
         "gtm", "restructur", "onboarding process"),
    ),
    Lead(
        "lead_reyes", "Reyes", "Strategy & Advisory",
        "Market entry, new lines of business, commercial strategy",
        ("new line of business", "market entry", "expand into",
         "commercial strategy", "new market", "explore"),
    ),
    Lead(
        "lead_whitfield", "Whitfield", "Finance & Transactions",
        "Diligence, underwriting, unit economics, FP&A",
        ("diligence", "underwrit", "unit economics", "acquisition",
         "fundrais", "financing", "default risk", "board"),
    ),
    Lead(
        "lead_amari", "Amari", "People & Change",
        "Onboarding curricula, training, calibration, tacit-knowledge transfer",
        ("onboarding", "training", "curriculum", "calibrat", "headcount",
         "hiring wave", "culture"),
    ),
)


def _score(lead: Lead, text_lower: str) -> int:
    return sum(1 for kw in lead.keywords if kw in text_lower)


def shortlist(service_line: ServiceLine, text: str) -> RoutingResult:
    """Rank the leads on `service_line` by keyword hits against `text`,
    return the top 1-2 as candidates.

    An uninformative shortlist (no keyword matched, or a genuine tie) is
    returned honestly rather than forcing a single guess - that's the whole
    point of shortlisting instead of picking. See docs/DECISIONS.md.
    """
    text_lower = text.lower()
    line_leads = [lead for lead in ROSTER if lead.service_line == service_line]
    if not line_leads:
        raise ValueError(f"No leads cover service line {service_line!r}")

    if len(line_leads) == 1:
        lead = line_leads[0]
        return RoutingResult(candidates=[
            RoutingCandidate(lead_id=lead.lead_id, rationale=f"{lead.name} - {lead.specialties}")
        ])

    ranked = sorted(line_leads, key=lambda lead: _score(lead, text_lower), reverse=True)
    top, runner_up = ranked[0], ranked[1]
    top_score, runner_score = _score(top, text_lower), _score(runner_up, text_lower)

    if top_score == 0:
        # No specialty keyword matched anyone on this line - an honest
        # "don't know" shortlist beats a confident-looking wrong guess.
        return RoutingResult(candidates=[
            RoutingCandidate(
                lead_id=lead.lead_id,
                rationale=f"{lead.name} - {lead.specialties} (no specialty keyword matched; "
                          f"showing both leads on {service_line})",
            )
            for lead in (top, runner_up)
        ])

    candidates = [RoutingCandidate(lead_id=top.lead_id, rationale=f"{top.name} - {top.specialties}")]
    if runner_score > 0 and runner_score >= top_score - 1:
        # Close enough to be a genuine two-way call, not a clear top pick.
        candidates.append(
            RoutingCandidate(lead_id=runner_up.lead_id, rationale=f"{runner_up.name} - {runner_up.specialties}")
        )
    return RoutingResult(candidates=candidates)
