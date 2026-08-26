"""All Airtable I/O for the jobs. Reads placements/forms/nudges; writes ONLY
to the Nudges table.

The Airtable token cannot be scoped to a single table (write scope is
base-wide), so the single-table guarantee is enforced HERE: every write in
this codebase goes through _write(), which hard-fails on any table other
than Nudges. No other module may call the Airtable API directly.

Field semantics: docs/data-dictionary.md. Ledger semantics: docs/decisions.md.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import date

from rules import FELLOW, SUPERVISOR, DueNudge, PriorNudge

BASE_ID = "appPaWOTEPjPt0BVc"          # Placements - MEL
PLACEMENTS = "tblPat6wJi9lYNOAt"
FELLOWS_FORMS = "tblcW7MLu3VQE1lnj"
SUPERVISORS_FORMS = "tblYfWuOxpPoCJP2s"
NUDGES = "tblHbHOy8GG3cV6JS"           # the ONLY writable table

# Placements are read through this view so pipeline rows (offers, matches in
# progress) never reach the rules. NOTE: the view's filter is part of the
# tool's behaviour — editing the view in Airtable changes who gets chased.
# The code-level silencers (paused/completed/no-start-date) still apply.
CURRENT_PLACEMENTS_VIEW = "viwzbNzzaDUCyn4KK"  # "Current Placements"

PLACEMENT_FIELDS = [
    "Name", "First Name", "Fellow Email", "Placement Org", "Cohort",
    "Start Date", "End Date", "Placement Paused?", "Placement Completed",
    "Expected Reports", "Actual Reports (Fellows)", "Actual Reports (Supervisors)",
    "Fellow Form Link", "Supervisor Form Link",
    "Email (from Supervisor)", "Supervisor First Name",
]
NUDGE_FIELDS = ["Placement", "Recipient", "Rung", "Status", "Created at", "Sent at"]

_RECIPIENT_TO_SELECT = {FELLOW: "Fellow", SUPERVISOR: "Supervisor"}
_SELECT_TO_RECIPIENT = {v: k for k, v in _RECIPIENT_TO_SELECT.items()}


def _token() -> str:
    token = os.environ.get("AIRTABLE_TOKEN")
    if not token:
        sys.exit("AIRTABLE_TOKEN is not set.")
    return token


def _request(method: str, url: str, payload: dict | None = None) -> dict:
    body = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=body, method=method, headers={
        "Authorization": f"Bearer {_token()}",
        **({"Content-Type": "application/json"} if body else {}),
    })
    try:
        with urllib.request.urlopen(req) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as e:
        # Status only — never echo the request or its headers (token inside).
        sys.exit(f"Airtable returned HTTP {e.code} on {method} {urllib.parse.urlparse(url).path}")


def _read_all(table_id: str, fields: list[str], view: str | None = None) -> list[dict]:
    records, offset = [], None
    while True:
        params = [("pageSize", "100")] + [("fields[]", f) for f in fields]
        if view:
            params.append(("view", view))
        if offset:
            params.append(("offset", offset))
        page = _request("GET", f"https://api.airtable.com/v0/{BASE_ID}/{table_id}"
                               f"?{urllib.parse.urlencode(params)}")
        records.extend(page["records"])
        offset = page.get("offset")
        if not offset:
            return records


def _write(method: str, table_id: str, path: str = "", payload: dict | None = None) -> dict:
    if table_id != NUDGES:  # the single-table write guarantee — do not remove
        raise RuntimeError(f"Refusing to write to table {table_id}: only Nudges is writable.")
    url = f"https://api.airtable.com/v0/{BASE_ID}/{table_id}{path}"
    return _request(method, url, payload)


# --- Reads -------------------------------------------------------------------

def fetch_placements() -> list[dict]:
    """Fixture-shaped records: Airtable record + form-date lists attached."""
    placements = _read_all(PLACEMENTS, PLACEMENT_FIELDS, view=CURRENT_PLACEMENTS_VIEW)
    fellow_forms = _read_all(FELLOWS_FORMS, ["Fellow", "Date Form Completed"])
    supervisor_forms = _read_all(SUPERVISORS_FORMS, ["Fellow", "Date"])
    for rec in placements:
        pid = rec["id"]
        rec["fellow_form_dates"] = sorted(
            fm["fields"]["Date Form Completed"] for fm in fellow_forms
            if pid in fm["fields"].get("Fellow", []) and fm["fields"].get("Date Form Completed"))
        rec["supervisor_form_dates"] = sorted(
            fm["fields"]["Date"] for fm in supervisor_forms
            if pid in fm["fields"].get("Fellow", []) and fm["fields"].get("Date"))
    return placements


def fetch_nudge_history() -> list[PriorNudge]:
    history = []
    for rec in _read_all(NUDGES, NUDGE_FIELDS):
        f = rec["fields"]
        if not (f.get("Placement") and f.get("Recipient") and f.get("Status")):
            continue  # half-filled manual row; the rules can't use it
        on = f.get("Sent at") if f.get("Status") == "Sent" else f.get("Created at")
        if not on:
            continue
        history.append(PriorNudge(
            placement_id=f["Placement"][0],
            recipient=_SELECT_TO_RECIPIENT[f["Recipient"]],
            rung=int(f.get("Rung") or 0),
            status=f["Status"],
            on=date.fromisoformat(on),
        ))
    return history


def fetch_pending_nudges() -> list[dict]:
    """Full Pending rows, for the poller (draft text + Slack thread included)."""
    rows = _read_all(NUDGES, NUDGE_FIELDS + ["Nudge", "Draft", "Slack thread", "To", "CC"])
    return [r for r in rows if r["fields"].get("Status") == "Pending"]


# --- Writes (Nudges only) ----------------------------------------------------

def create_pending_nudge(due: DueNudge, draft: str, today: date) -> str:
    rec = _write("POST", NUDGES, payload={"fields": {
        "Nudge": f"{due.first_name} – {due.recipient} – rung {due.rung} – {today.isoformat()}",
        "Placement": [due.placement_id],
        "Recipient": _RECIPIENT_TO_SELECT[due.recipient],
        "Rung": due.rung,
        "Depth": due.depth,
        "Supervisor CC'd": due.cc_supervisor,
        "Status": "Pending",
        "Draft": draft,
        "To": due.email,
        **({"CC": due.supervisor_email} if due.cc_supervisor else {}),
        "Created at": today.isoformat(),
    }})
    return rec["id"]


def set_slack_thread(record_id: str, permalink: str) -> None:
    _write("PATCH", NUDGES, f"/{record_id}",
           {"fields": {"Slack thread": permalink}})


def update_draft(record_id: str, revised: str, previous: str) -> None:
    """Revisions stack newest-first so the ledger keeps the full history."""
    stacked = f"{revised}\n\n--- superseded draft ---\n{previous}"
    _write("PATCH", NUDGES, f"/{record_id}", {"fields": {"Draft": stacked}})


def stamp_sent(record_id: str, approved_by: str, when: date) -> None:
    _write("PATCH", NUDGES, f"/{record_id}", {"fields": {
        "Status": "Sent", "Approved by": approved_by, "Sent at": when.isoformat()}})


def stamp_rejected(record_id: str, decided_by: str) -> None:
    _write("PATCH", NUDGES, f"/{record_id}", {"fields": {
        "Status": "Rejected", "Approved by": decided_by}})
