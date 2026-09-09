"""
triage.py - the pipeline that turns one Enquiry into a TriageDecision.

Stage 1 (service_line) and Stage 2 (complexity) are independent Claude calls
against different evidence bases - see docs/DECISIONS.md ("Treated the three
outputs as separate problems"). Stage 3 (routing) is a deterministic lookup,
not a model call (src/leads.py). Stage 4 (verifier) is a single Claude call
that reviews the assembled draft as a whole and decides whether a human
should trust it as a starting point or take the enquiry from scratch. Three
LLM calls total per enquiry - see docs/DECISIONS.md for the alternatives
considered and rejected.

Error handling is deliberately minimal: no retries, no backoff. This is a
batch script run by a human who re-runs it on failure, not a service with an
uptime target - see CLAUDE.md's scale rules. A raised exception here is left
for the caller (evals/run_eval.py) to catch and count, rather than papered
over with a fake decision.
"""

from __future__ import annotations

import anthropic

from src.config import ANTHROPIC_API_KEY, MODEL
from src.leads import shortlist
from src.schema import (
    ComplexityResult,
    Enquiry,
    RoutingResult,
    ServiceLineResult,
    TriageDecision,
    VerifierResult,
)

_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

SERVICE_LINE_SYSTEM_PROMPT = """\
You are triaging inbound enquiries for a professional services firm, deciding
which service line should own each one. You are replacing an experienced
human analyst's judgment, not running a keyword search - read for what the
client actually needs, not which buzzwords appear.

The five service lines:
- Technology & Data: building or fixing software, data pipelines, analytics,
  ML models, or system integrations. The client wants something BUILT.
- Risk & Compliance: independent assessments, audits, and readiness reviews
  against a named standard, regulation, or examiner expectation. The client
  wants to be EXAMINED or CERTIFIED, or wants to prepare for someone else
  examining them.
- Strategy & Advisory: process redesign, operating model design, market
  entry, or new-line-of-business decisions. The client wants a POINT OF VIEW
  or a REDESIGN, not a build and not an audit.
- Finance & Transactions: financial or operational diligence, underwriting
  review, unit economics. Usually tied to a deal, a raise, or a board
  deadline.
- People & Change: onboarding, training, calibration, or organizational
  adoption problems. The client's actual problem is that PEOPLE lack a
  consistent process or do not trust or use something that already exists.

Watch for these traps:
- AI/ML vocabulary does not mean Technology & Data. A request to assess or
  govern an AI system (e.g. against a regulatory framework) is Risk &
  Compliance; a request to build or improve one is Technology & Data.
- A technical-sounding pain point can have a people root cause. If the real
  blocker is inconsistent human judgment, undocumented tacit knowledge, or a
  team that never adopted a prior tool, building more technology on top of
  it encodes the inconsistency rather than fixing it - that is People &
  Change (or Strategy & Advisory), even if the client asks for a tool.
- When two internal teams or theories are in conflict, or the text carries
  genuinely contradictory signals, and someone needs to determine which
  framing is right before real work can start, name a secondary service
  line and say so in your rationale rather than silently picking one and
  hiding the tension.
- Some enquiries are outside the firm's service lines entirely: a legal
  opinion on a live transaction meant to route around a specific
  regulator's jurisdiction, requests carrying reputational or ethical
  exposure beyond normal service delivery, vendor pitches, job
  applications, or existing-client support/account requests. These are not
  triage failures to force into a service line - if the enquiry does not
  fit, say so plainly in your rationale; a downstream check decides whether
  to escalate rather than route it.

Given one enquiry, decide the primary service line, an optional secondary
service line if a real second workstream is present, and give a rationale a
service-line lead could read and immediately understand - name the specific
evidence in the text you used, and name what you chose not to weight (e.g. a
buzzword) if it is likely to mislead someone skimming.
"""

COMPLEXITY_SYSTEM_PROMPT = """\
You are estimating how complex an inbound client enquiry will be to scope
and deliver, on behalf of an experienced analyst. This is a judgment call,
not a fact lookup - there is no formula, and the same words can describe
wildly different amounts of real work depending on context.

Use three levels:
- simple: a lead could size this engagement on one call. The ask is
  bounded, the client has already done real scoping (they name the
  deliverable, what is in and out of scope, and any hard constraints), and
  nothing in the context suggests hidden surface area.
- moderate: the ask itself is well-defined, but sizing it precisely
  requires seeing something the client has not shown yet (an existing
  system's actual state, a pipeline's real shape, data quality) before
  effort can be estimated.
- complex: multiple workstreams, disciplines, or stakeholders are
  involved; the request depends on solving another problem first (a
  scoping call, a diagnostic, a data-quality problem) before the real
  engagement is even known; or the client's own account of the problem is
  contradictory or underspecified in a way that changes the shape of the
  work depending on the answer.

Do not infer complexity from length or vocabulary density. A short, plainly
stated enquiry can be complex (because the actual blocker is buried
underneath the framing the client is reaching for), and a long, detailed
one can be simple (a client who has already scoped their own request
thoroughly). Do not equate "the client called it quick or simple" with
actual complexity - weigh what their own stated context implies against
what they are asking for, and say so in your rationale if the two disagree.

Give a rationale a lead could use to decide whether to trust your estimate:
name the specific thing that makes this bounded or open-ended, not just a
restatement of the request.
"""

VERIFIER_SYSTEM_PROMPT = """\
You are the last check before a draft triage decision reaches a human
analyst. You did not produce the service-line, complexity, or routing
guesses below - another process did, working from the enquiry text alone.
Your job is to decide whether that draft is trustworthy enough to hand to a
human as a starting point, or whether the human should instead triage this
enquiry from scratch with no assistance from the draft.

Sign off (sign_off: true) only if, reading the original enquiry text fresh:
- the proposed service line(s) are actually supported by what the client
  wrote, not just plausible;
- the complexity estimate reflects real signal in the text, not just
  restated length or vocabulary;
- the routing shortlist's rationale is consistent with the proposed service
  line and with what the enquiry actually describes needing.

Do not sign off (sign_off: false), and set abstain_trigger, when:
- "low_confidence": the draft looks like a reasonable guess but the
  enquiry text is too thin, contradictory, or genuinely ambiguous between
  multiple defensible readings for you to independently confirm it - a
  human should triage this one directly rather than start from an
  unreliable draft;
- "above_authority": regardless of how confident the draft looks, the
  enquiry itself is not something a junior analyst (or this system) has
  standing to route alone - for example it is really a request for a legal
  opinion on a specific live transaction or regulatory structuring
  question, carries reputational or ethical exposure beyond normal service
  delivery, or otherwise needs a partner's engagement-risk judgment before
  anyone accepts it. This applies even if the draft's service-line guess is
  technically defensible - the point is that the decision needs escalation,
  not a better guess.

State your reason in one or two sentences a human reviewing the log could
act on without re-reading the whole enquiry.
"""


def _call_structured(system_prompt: str, user_content: str, output_model, tool_name: str):
    tool = {
        "name": tool_name,
        "description": f"Report the {tool_name}.",
        "input_schema": output_model.model_json_schema(),
    }
    response = _client.messages.create(
        model=MODEL,
        max_tokens=1024,
        system=system_prompt,
        tools=[tool],
        tool_choice={"type": "tool", "name": tool_name},
        messages=[{"role": "user", "content": user_content}],
    )
    for block in response.content:
        if block.type == "tool_use" and block.name == tool_name:
            return output_model.model_validate(block.input)
    raise RuntimeError(f"model did not call the {tool_name} tool")


def _enquiry_text(enquiry: Enquiry) -> str:
    form = enquiry.form
    return (
        f"Industry: {form.industry}\n"
        f"Company size: {form.company_size}\n"
        f"Stated urgency: {form.urgency}\n\n"
        f"Description:\n{form.description}"
    )


def classify_service_line(enquiry: Enquiry) -> ServiceLineResult:
    return _call_structured(
        SERVICE_LINE_SYSTEM_PROMPT, _enquiry_text(enquiry), ServiceLineResult, "service_line_result"
    )


def assess_complexity(enquiry: Enquiry) -> ComplexityResult:
    return _call_structured(
        COMPLEXITY_SYSTEM_PROMPT, _enquiry_text(enquiry), ComplexityResult, "complexity_result"
    )


def verify(
    enquiry: Enquiry,
    service_line: ServiceLineResult,
    complexity: ComplexityResult,
    routing: RoutingResult,
) -> VerifierResult:
    draft = (
        f"Proposed service line: {service_line.primary}"
        + (f" (secondary: {service_line.secondary})" if service_line.secondary else "")
        + f"\nService line rationale: {service_line.rationale}\n\n"
        f"Proposed complexity: {complexity.value}\n"
        f"Complexity rationale: {complexity.rationale}\n\n"
        "Proposed routing shortlist:\n"
        + "\n".join(f"- {c.lead_id}: {c.rationale}" for c in routing.candidates)
    )
    user_content = f"{_enquiry_text(enquiry)}\n\n---\nDraft triage decision to review:\n{draft}"
    return _call_structured(VERIFIER_SYSTEM_PROMPT, user_content, VerifierResult, "verifier_result")


def triage(enquiry: Enquiry) -> TriageDecision:
    service_line = classify_service_line(enquiry)
    complexity = assess_complexity(enquiry)
    routing = shortlist(service_line.primary, enquiry.form.description)
    verifier = verify(enquiry, service_line, complexity, routing)

    return TriageDecision(
        enquiry_id=enquiry.id,
        submitted_at=enquiry.submitted_at,
        service_line=service_line,
        complexity=complexity,
        routing=routing,
        verifier=verifier,
        abstain=not verifier.sign_off,
    )
