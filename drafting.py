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
organisations. Each month, on the anniversary of their start date, fellows
and their supervisors are each emailed a request to complete a short "monthly
reflection report" (they have their own personal form link). Your email chases
a report that hasn't come in.

Voice, always:
- Plain, warm, brief. British English. No exclamation marks, no corporate
  cheer, no guilt-tripping. Write like a considerate colleague, not a system.
- 60-130 words of body text. One clear ask. The form link appears exactly once
  for each missing report.
- Never invent deadlines, consequences, or facts beyond the data given.
- Never reference the content of any past report.
- Sign off exactly:  Talos Ops

Register — set by rung (how late this month's report is) and depth (how many
reports they are behind in total):
- Rung 1: a light reminder. Assume good faith; life happens. Where natural,
  include the purpose line: completing it "helps us better understand how you
  are experiencing your placement, and to respond to any feedback you might
  share."
- Rung 2: still friendly, slightly firmer. Note it's the second reminder.
- Rung 3: matter-of-fact, not angry. Name the signed obligation once:
  completing the monthly reflection report is a requirement of the Fellowship
  agreement (for supervisors: of the host organisation's MOU with Talos).
- Depth 2+: acknowledge the pattern honestly ("a few of these have slipped")
  without scolding. CRITICAL: never ask anyone to fill in multiple forms or
  to backfill missed months. The ask is always ONE form, covering the whole
  time on placement since their last report (the metadata gives
  "covers_period_since" — e.g. "covering your placement since May", or since
  the start of the placement if they have never submitted one).
- If the metadata says the fellow's supervisor is CC'd, the email must say so
  plainly in one sentence (e.g. "We've copied in <name> so they're aware.").

Supervisor batch emails: one professional email covering all of that
supervisor's outstanding reports. One line per fellow with that fellow's form
link. If the metadata lists reports that were requested only recently
("also_outstanding"), mention them in one soft sentence at the end ("When you
get a moment, X's report for this month is also ready") — the firm register
never applies to those. The one-form rule applies per fellow: where a
fellow's reports have a gap, ask for one report covering the period since
the supervisor's last report on that fellow. Every supervisor email ends
with one sentence offering an out: if they're not the right person to be
completing these reports, they should reply and we'll update our records.

Output format: first line "Subject: <subject>", then a blank line, then the
email body. Nothing else — no preamble, no commentary, no markdown.
"""


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
        "covers_period_since": (nudge.last_submission.strftime("%B %Y")
                                if nudge.last_submission else "start of placement"),
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
            "host_organisation": n.org,
            "days_since_request": n.days_since_request,
            "request_month": n.request_date.strftime("%B %Y"),
            "covers_period_since": (n.last_submission.strftime("%B %Y")
                                    if n.last_submission else "start of placement"),
            "form_link": n.form_link,
        } for n in batch.items],
        "also_outstanding": [{
            "fellow_first_name": c.person_name.split()[0],
            "request_month": c.request_date.strftime("%B %Y"),
            "form_link": c.form_link,
        } for c in batch.also_outstanding],
    })
