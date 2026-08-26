"""Form-completion rates, for tracking whether the nudges move the number.
Baseline and method: docs/metrics.md. Reads counting fields only.
Usage: python3 scripts/completion_stats.py  (needs AIRTABLE_TOKEN)"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from airtable_client import PLACEMENTS, _read_all  # noqa: E402

FIELDS = ["Expected Reports", "Actual Reports (Fellows)",
          "Actual Reports (Supervisors)", "Placement Paused?", "Placement Completed"]


def report(rows: list[tuple], label: str) -> None:
    expected = sum(r[0] for r in rows)
    if not expected:
        return
    fellows = sum(min(r[1], r[0]) for r in rows)
    supervisors = sum(min(r[2], r[0]) for r in rows)
    print(f"{label}: n={len(rows)}, expected={expected}")
    print(f"  fellows {100 * fellows / expected:.0f}%  "
          f"supervisors {100 * supervisors / expected:.0f}%  "
          f"combined {100 * (fellows + supervisors) / (2 * expected):.0f}%  (capped)")


def main() -> None:
    rows = []
    for rec in _read_all(PLACEMENTS, FIELDS):  # whole table: history included
        f = rec["fields"]
        expected = int(f.get("Expected Reports") or 0)
        if expected <= 0:
            continue
        status = ("completed" if f.get("Placement Completed")
                  else "paused" if f.get("Placement Paused?") else "current")
        rows.append((expected, int(f.get("Actual Reports (Fellows)") or 0),
                     int(f.get("Actual Reports (Supervisors)") or 0), status))
    report(rows, "ALL placements")
    report([r for r in rows if r[3] == "current"], "CURRENT placements")
    report([r for r in rows if r[3] == "completed"], "COMPLETED cohorts")
    print("\nBaseline (26 Aug 2026): current combined 76%, all-time 62% — "
          "log new measurements in docs/metrics.md")


if __name__ == "__main__":
    main()
