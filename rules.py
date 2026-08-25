"""Deterministic rules engine: WHO gets nudged and WHEN. No AI in this file.

Data dictionary: docs/data-dictionary.md (field semantics verified against the
live base and a real fixture, 25 Aug 2026). The monthly timeline per placement:

  day 0   month-anniversary of Start Date: Airtable emails the form request
  day 7   nudge 1 due if the current month's form is not in
  day 10  the base's Expected Reports increments (built-in grace)
  day 14  nudge 2 due
  day 21  nudge 3 due; then silence until the next month-anniversary

Ladder decisions (docs/decisions.md):
- "Current month's form done" is decided by SUBMISSION DATES (any submission
  on/after the request date), never by Expected/Actual counts alone.
- Depth (Expected - Actual, min 1 while nudging) shades tone and, at
  CC_SUPERVISOR_DEPTH, CCs the fellow's supervisor on the fellow's nudge.
- Rungs are climbed one at a time: the next rung is one more than the last
  rung sent this month, regardless of elapsed time. Prevents greeting someone
  with rung-3 firmness on the tool's first cycle.
- A Rejected (skipped) nudge silences that person+role for the month.
- A Pending draft (unapproved) blocks drafting the same person+role again.
- Paused / completed placements and records without a Start Date are never
  chased; the latter are reported as unprocessable so a human sees them.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass, field
from datetime import date

# --- Config: the ladder. Change values here, not logic below. ---------------
NUDGE_DAY_THRESHOLDS = (7, 14, 21)  # days after request date when rungs 1-3 unlock
MAX_NUDGES_PER_MONTH = 3
CC_SUPERVISOR_DEPTH = 3      # fellow this many forms behind -> supervisor CC'd
HEAVY_TONE_DEPTH = 2         # depth at which the register acknowledges a pattern
MIN_DAYS_BETWEEN_NUDGES = 6  # per person+placement, so late approvals don't stack

FELLOW = "fellow"
SUPERVISOR = "supervisor"


@dataclass(frozen=True)
class PriorNudge:
    """One row of the Nudges ledger, as the rules see it."""
    placement_id: str
    recipient: str  # FELLOW or SUPERVISOR
    rung: int
    status: str     # "Pending" | "Sent" | "Rejected"
    on: date        # created date (Pending/Rejected) or sent date (Sent)


@dataclass
class DueNudge:
    """Everything the drafting prompt needs. Metadata only — never form content."""
    placement_id: str
    recipient: str
    person_name: str
    first_name: str
    email: str
    org: str
    rung: int
    depth: int
    request_date: date
    days_since_request: int
    form_link: str
    cc_supervisor: bool = False
    supervisor_email: str = ""
    supervisor_first_name: str = ""
    reason: str = ""


@dataclass
class RulesResult:
    due: list[DueNudge] = field(default_factory=list)
    silenced: list[str] = field(default_factory=list)       # paused/completed
    unprocessable: list[str] = field(default_factory=list)  # "name: why" — show a human
    quiet: list[str] = field(default_factory=list)          # checked, nothing due


def add_months(d: date, n: int) -> date:
    """d plus n calendar months, day clamped (Jan 31 + 1 month = Feb 28/29)."""
    y = d.year + (d.month - 1 + n) // 12
    m = (d.month - 1 + n) % 12 + 1
    return date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


def latest_request_date(start: date, today: date) -> date | None:
    """The most recent month-anniversary of start on or before today.
    None if the first anniversary hasn't arrived (no form ever requested)."""
    if today < add_months(start, 1):
        return None
    k = 1
    while add_months(start, k + 1) <= today:
        k += 1
    return add_months(start, k)


def current_form_done(submissions: list[date], request: date) -> bool:
    return any(s >= request for s in submissions)


def _rung_unlocked(days_since_request: int) -> int:
    """Highest rung the calendar allows (0 = none yet)."""
    unlocked = 0
    for i, threshold in enumerate(NUDGE_DAY_THRESHOLDS, start=1):
        if days_since_request >= threshold:
            unlocked = i
    return unlocked


def _next_rung(history: list[PriorNudge], request: date, today: date) -> int | None:
    """The rung to send now for one person+placement, or None.

    history must already be filtered to this placement_id + recipient.
    """
    this_month = [h for h in history if h.on >= request]
    if any(h.status == "Rejected" for h in this_month):
        return None  # an explicit skip silences the month
    if any(h.status == "Pending" for h in this_month):
        return None  # a draft is already awaiting approval
    sent = [h for h in this_month if h.status == "Sent"]
    if len(sent) >= MAX_NUDGES_PER_MONTH:
        return None
    if sent:
        last = max(sent, key=lambda h: h.on)
        if (today - last.on).days < MIN_DAYS_BETWEEN_NUDGES:
            return None
        candidate = min(last.rung + 1, len(NUDGE_DAY_THRESHOLDS))
        if candidate <= last.rung:
            return None  # already at the top rung
    else:
        candidate = 1
    if candidate > _rung_unlocked((today - request).days):
        return None  # calendar hasn't unlocked it yet
    return candidate


def _first(value) -> str:
    """Airtable lookups arrive as lists; take the first entry or empty."""
    if isinstance(value, list):
        return value[0] if value else ""
    return value or ""


def who_needs_nudging(placements: list[dict], history: list[PriorNudge],
                      today: date) -> RulesResult:
    """placements: fixture-shaped records — Airtable `fields` dict plus
    `fellow_form_dates` / `supervisor_form_dates` ISO date lists."""
    result = RulesResult()
    by_key: dict[tuple[str, str], list[PriorNudge]] = {}
    for h in history:
        by_key.setdefault((h.placement_id, h.recipient), []).append(h)

    for rec in placements:
        f = rec["fields"]
        name = f.get("Name", rec["id"])

        if f.get("Placement Paused?") or f.get("Placement Completed"):
            result.silenced.append(name)
            continue
        if not f.get("Start Date"):
            result.unprocessable.append(
                f"{name}: no Start Date — cannot compute anything; "
                f"fix the record (Placement Org says: {f.get('Placement Org', '')!r})")
            continue

        start = date.fromisoformat(f["Start Date"])
        request = latest_request_date(start, today)
        if request is None:
            result.quiet.append(f"{name}: first form not yet due")
            continue

        depth_fellow = max(1, int(f.get("Expected Reports") or 0)
                           - int(f.get("Actual Reports (Fellows)") or 0))
        depth_supervisor = max(1, int(f.get("Expected Reports") or 0)
                               - int(f.get("Actual Reports (Supervisors)") or 0))
        supervisor_email = _first(f.get("Email (from Supervisor)"))
        supervisor_first = _first(f.get("Supervisor First Name"))
        days = (today - request).days

        for recipient, submissions, depth in (
            (FELLOW, rec.get("fellow_form_dates", []), depth_fellow),
            (SUPERVISOR, rec.get("supervisor_form_dates", []), depth_supervisor),
        ):
            dates = [date.fromisoformat(s) for s in submissions]
            if current_form_done(dates, request):
                result.quiet.append(f"{name} ({recipient}): current month submitted")
                continue
            rung = _next_rung(by_key.get((rec["id"], recipient), []), request, today)
            if rung is None:
                result.quiet.append(f"{name} ({recipient}): no rung due")
                continue

            if recipient == FELLOW:
                email, first, link = f.get("Fellow Email", ""), f.get("First Name", ""), f.get("Fellow Form Link", "")
            else:
                email, first, link = supervisor_email, supervisor_first, f.get("Supervisor Form Link", "")
            if not email:
                result.unprocessable.append(f"{name}: no {recipient} email on record")
                continue

            cc = (recipient == FELLOW and depth >= CC_SUPERVISOR_DEPTH
                  and bool(supervisor_email))
            result.due.append(DueNudge(
                placement_id=rec["id"], recipient=recipient,
                person_name=name if recipient == FELLOW else _first(f.get("Supervisor First Name")) or "supervisor",
                first_name=first, email=email, org=f.get("Placement Org", ""),
                rung=rung, depth=depth, request_date=request,
                days_since_request=days, form_link=link,
                cc_supervisor=cc, supervisor_email=supervisor_email,
                supervisor_first_name=supervisor_first,
                reason=(f"{recipient} form for request of {request.isoformat()} not submitted; "
                        f"{days} days since request; {depth} form(s) behind"
                        + ("; supervisor CC" if cc else "")),
            ))
    return result
