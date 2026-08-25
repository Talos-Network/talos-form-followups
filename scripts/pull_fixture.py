"""Pull 3-4 deliberately varied Placements records into fixture.json.

Reads AIRTABLE_TOKEN from the environment (set via `read -s`, never a file).
Requests ONLY whitelisted fields, so qualitative form answers (rich text,
satisfaction ratings) never leave Airtable. fixture.json contains real
fellows' data: it is gitignored and this script refuses to run otherwise.

Usage: python3 scripts/pull_fixture.py
"""

import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path

BASE_ID = "appPaWOTEPjPt0BVc"  # Placements - MEL
PLACEMENTS = "tblPat6wJi9lYNOAt"
FELLOWS_FORMS = "tblcW7MLu3VQE1lnj"
SUPERVISORS_FORMS = "tblYfWuOxpPoCJP2s"

# Everything the rules engine and drafting prompt will ever need — and
# nothing qualitative. See docs/data-dictionary.md for what each field means.
PLACEMENT_FIELDS = [
    "Name", "First Name", "Fellow Email", "Placement Org", "Cohort",
    "Start Date", "End Date", "Placement Paused?", "Placement Completed",
    "Months Since Start", "Expected Reports",
    "Actual Reports (Fellows)", "Actual Reports (Supervisors)",
    "Status (Fellows)", "Status (Supervisors)",
    "Updates? (Fellows)", "Updates? (Supervisors)",
    "Last Form Completed (Supervisors)", "Last Form Completed (Fellows)",
    "Fellow Form Link", "Supervisor Form Link",
    "Supervisor", "Email (from Supervisor)", "Supervisor First Name",
]
# From the forms tables we take ONLY the link back to the placement and the
# submission date — never the answers.
FELLOWS_FORM_FIELDS = ["Fellow", "Date Form Completed"]
SUPERVISORS_FORM_FIELDS = ["Fellow", "Date"]


def fetch_all(table_id: str, fields: list[str]) -> list[dict]:
    token = os.environ.get("AIRTABLE_TOKEN")
    if not token:
        sys.exit("AIRTABLE_TOKEN is not set. Run:  read -s AIRTABLE_TOKEN && export AIRTABLE_TOKEN")
    records, offset = [], None
    while True:
        params = [("pageSize", "100")] + [("fields[]", f) for f in fields]
        if offset:
            params.append(("offset", offset))
        url = f"https://api.airtable.com/v0/{BASE_ID}/{table_id}?{urllib.parse.urlencode(params)}"
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
        try:
            with urllib.request.urlopen(req) as resp:
                page = json.load(resp)
        except urllib.error.HTTPError as e:
            # Never echo the request (the token is in its headers); status is enough.
            sys.exit(f"Airtable returned HTTP {e.code} for table {table_id}. "
                     f"403 usually means the token lacks a scope or base access.")
        records.extend(page["records"])
        offset = page.get("offset")
        if not offset:
            return records


def pick_varied(placements: list[dict]) -> list[dict]:
    """One of each situation the rules engine must handle, up to 4 records."""
    def f(r, key, default=None):
        return r["fields"].get(key, default)

    buckets = {
        "paused_or_completed": lambda r: f(r, "Placement Paused?") or f(r, "Placement Completed"),
        "brand_new": lambda r: f(r, "Expected Reports", 0) == 0 and not f(r, "Placement Completed"),
        "behind": lambda r: f(r, "Expected Reports", 0) > f(r, "Actual Reports (Fellows)", 0)
                            and not f(r, "Placement Paused?") and not f(r, "Placement Completed"),
        "up_to_date": lambda r: f(r, "Expected Reports", 0) > 0
                                and f(r, "Actual Reports (Fellows)", 0) >= f(r, "Expected Reports", 0)
                                and not f(r, "Placement Paused?") and not f(r, "Placement Completed"),
    }
    picked, seen = [], set()
    for label, test in buckets.items():
        for r in placements:
            if r["id"] not in seen and test(r):
                r["_fixture_reason"] = label
                picked.append(r)
                seen.add(r["id"])
                break
    return picked


def main() -> None:
    repo = Path(__file__).resolve().parent.parent
    gitignore = (repo / ".gitignore").read_text() if (repo / ".gitignore").exists() else ""
    if "fixture.json" not in gitignore:
        sys.exit("Refusing to run: fixture.json is not in .gitignore.")

    placements = fetch_all(PLACEMENTS, PLACEMENT_FIELDS)
    fellow_forms = fetch_all(FELLOWS_FORMS, FELLOWS_FORM_FIELDS)
    supervisor_forms = fetch_all(SUPERVISORS_FORMS, SUPERVISORS_FORM_FIELDS)
    print(f"Fetched {len(placements)} placements, {len(fellow_forms)} fellow forms, "
          f"{len(supervisor_forms)} supervisor forms.")

    picked = pick_varied(placements)
    for rec in picked:
        pid = rec["id"]
        rec["fellow_form_dates"] = sorted(
            fm["fields"]["Date Form Completed"]
            for fm in fellow_forms
            if pid in fm["fields"].get("Fellow", []) and fm["fields"].get("Date Form Completed")
        )
        rec["supervisor_form_dates"] = sorted(
            fm["fields"]["Date"]
            for fm in supervisor_forms
            if pid in fm["fields"].get("Fellow", []) and fm["fields"].get("Date")
        )

    out = repo / "fixture.json"
    out.write_text(json.dumps({"pulled_at": "2026-08-25", "placements": picked}, indent=2))
    print(f"\nWrote {out} with {len(picked)} records:")
    for rec in picked:
        fields = rec["fields"]
        print(f"  - {fields.get('Name', '?')} ({rec['_fixture_reason']}): "
              f"expected {fields.get('Expected Reports', 0)}, "
              f"actual {fields.get('Actual Reports (Fellows)', 0)}, "
              f"fellow submissions on {rec['fellow_form_dates'] or 'none'}")


if __name__ == "__main__":
    main()
