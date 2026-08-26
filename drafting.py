"""The judgment layer: one Claude call per email. Claude decides WHAT the
nudge says — never WHO gets one or WHEN (that's rules.py) and never whether
it SENDS (that's a human in Slack).

The prompt receives METADATA ONLY (hard rule 5): names, rung, depth, dates,
form links. Form answers never enter this module.

VOICE — this system prompt is where the programme's voice lives. Iterate on
it with Steve; docs/decisions.md #2 records the agreed registers.
"""

from __future__ import annotations

import json

import anthropic

from rules import DueNudge, SupervisorBatch

MODEL = "claude-opus-5"

VOICE = """\
You draft chase-up emails for Talos Network's fellowship programme. They are
sent from the shared mailbox ops@talosnetwork.org and signed "Talos Ops".

About the programme: Talos fellows do placements at technology-policy host
organisations. Each month, on the anniversary of their start date, a fellow
is emailed a request to complete a monthly progress report, and their
supervisor is emailed a request to complete a progress report on that
fellow's placement. Everyone has their own personal form link. Your email
chases a report that hasn't come in.

Terminology: always "progress report" (or just "report"). Never "reflection
report".

Voice, always:
- Plain, warm, brief. British English. No exclamation marks, no corporate
  cheer, no guilt-tripping. Write like a considerate colleague, not a system.
- Light never means optional: no "whenever you have a spare moment", "no
  rush", "it's fine". The ask is simply made, kindly.
- 50-120 words of body text. One clear ask. Each form link appears exactly
  once.
- Never name the host organisation back at the recipient — they work there.
- Never invent deadlines, consequences, or facts beyond the data given.
- Never reference the content of any past report.
- Never explain the mechanics of the reporting system (no talk of backfilling,
  catching up on individual forms, or how the forms work).
- Sign off exactly:  Talos Ops

Register — set by rung (how late the current report is) and depth (how many
request cycles since their last report):
- Rung 1: a light reminder. Assume good faith; life happens. Where natural,
  include the purpose line: completing it "helps us better understand how you
  are experiencing your placement, and to respond to any feedback you might
  share."
- Rung 2: still friendly, slightly firmer. Note it's the second reminder.
- Rung 3: matter-of-fact, not angry. Name the signed obligation once:
  completing the monthly progress report is a requirement of the Fellowship
  agreement (for supervisors: of the host organisation's MOU with Talos).
- Depth 1: keep it simple — "we haven't yet received your most recent
  progress report". Do NOT spell out what period it covers.
- Depth 2+: acknowledge the pattern honestly ("a few of these have slipped")
  without scolding, then state plainly that this report should cover their
  placement since the exact date in "report_covers_since" (e.g. "since
  12 May 2026"). One report, one date, no further explanation.
- If the metadata says the fellow's supervisor is CC'd, the email must say so
  plainly in one sentence (e.g. "We've copied in <name> so they're aware.").

Supervisor emails: the report is THEIRS, about the fellow — say "your
progress report on <fellow>'s placement", never "<fellow>'s report".
- One fellow: a normal prose email, same registers as above.
- Several fellows: a short line per fellow with that fellow's form link;
  where a fellow's entry has depth 2+, its line names the covers-since date.
- If the metadata lists reports requested only recently ("also_outstanding"),
  mention them in one soft sentence at the end — the firm register never
  applies to those.
- Every supervisor email ends with one sentence offering an out: if they're
  not the right person to be completing these reports, they can reply and
  we'll update our records.

Output format: first line "Subject: <subject>", then a blank line, then the
email body. Nothing else — no preamble, no commentary, no markdown.
"""


SUPERSEDED_DIVIDER = "\n\n--- superseded draft ---\n"


def split_draft(draft_field: str) -> tuple[str, str]:
    """(subject, body) of the CURRENT draft from a ledger Draft field —
    revisions are stacked newest-first above a superseded divider."""
    current = draft_field.split(SUPERSEDED_DIVIDER, 1)[0].strip()
    first, _, body = current.partition("\n")
    return first.removeprefix("Subject:").strip(), body.strip()


def revise_draft(client: anthropic.Anthropic, current_draft: str,
                 instructions: str) -> tuple[str, str]:
    """Revise per the approver's instructions; all voice rules still apply."""
    return _call(client, {
        "email_type": "revision",
        "current_draft": current_draft,
        "approver_instructions": instructions,
        "note": ("Revise the draft according to the approver's instructions. "
                 "Keep everything else, including all voice rules, intact."),
    })


def _covers_since(nudge) -> str:
    d = nudge.last_submission or nudge.placement_start
    return f"{d.day} {d:%B %Y}" if d else "start of placement"


def _call(client: anthropic.Anthropic, payload: dict) -> tuple[str, str]:
    """Returns (subject, body). Raises on refusal or malformed output so the
    draft job can surface the failure in the summary instead of half-sending."""
    response = client.messages.create(
        model=MODEL,
        max_tokens=2000,
        system=VOICE,
        messages=[{"role": "user", "content": json.dumps(payload, indent=2)}],
    )
    if response.stop_reason == "refusal":
        raise RuntimeError(f"Model declined to draft: {response.stop_details}")
    text = "".join(b.text for b in response.content if b.type == "text").strip()
    first, _, body = text.partition("\n")
    if not first.startswith("Subject:") or not body.strip():
        raise RuntimeError(f"Draft output not in Subject/body format: {text[:80]!r}")
    return first.removeprefix("Subject:").strip(), body.strip()


def draft_fellow_nudge(client: anthropic.Anthropic, nudge: DueNudge) -> tuple[str, str]:
    return _call(client, {
        "email_type": "fellow_nudge",
        "fellow_first_name": nudge.first_name,
        "host_organisation": nudge.org,
        "rung": nudge.rung,
        "depth_reports_behind": nudge.depth,
        "days_since_request": nudge.days_since_request,
        "request_month": nudge.request_date.strftime("%B %Y"),
        "report_covers_since": _covers_since(nudge),
        "form_link": nudge.form_link,
        "supervisor_cc": (
            {"cc_applied": True, "supervisor_first_name": nudge.supervisor_first_name}
            if nudge.cc_supervisor else {"cc_applied": False}),
    })


def draft_supervisor_batch(client: anthropic.Anthropic, batch: SupervisorBatch) -> tuple[str, str]:
    return _call(client, {
        "email_type": "supervisor_batch",
        "supervisor_first_name": batch.first_name,
        "rung": batch.rung,
        "depth_reports_behind": batch.depth,
        "missing_reports": [{
            "fellow_first_name": n.person_name.split()[0],
            "depth": n.depth,
            "days_since_request": n.days_since_request,
            "request_month": n.request_date.strftime("%B %Y"),
            "report_covers_since": _covers_since(n),
            "form_link": n.form_link,
        } for n in batch.items],
        "also_outstanding": [{
            "fellow_first_name": c.person_name.split()[0],
            "request_month": c.request_date.strftime("%B %Y"),
            "form_link": c.form_link,
        } for c in batch.also_outstanding],
    })
