"""Read-only smoke test of airtable_client against the live base.
Usage: python3 scripts/smoke_airtable.py (needs AIRTABLE_TOKEN in the shell)"""

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from airtable_client import fetch_nudge_history, fetch_placements  # noqa: E402
from rules import who_needs_nudging  # noqa: E402

placements = fetch_placements()
history = fetch_nudge_history()
print(f"Placements: {len(placements)} | Nudge history rows: {len(history)}")

result = who_needs_nudging(placements, history, date.today())
print(f"\nAcross the WHOLE programme today: {len(result.due)} nudge(s) due, "
      f"{len(result.silenced)} silenced, {len(result.unprocessable)} unprocessable, "
      f"{len(result.quiet)} quiet.")
for n in result.due:
    cc = " +CC supervisor" if n.cc_supervisor else ""
    print(f"  - {n.recipient} rung {n.rung} depth {n.depth}: {n.first_name} re {n.org}{cc}")
for u in result.unprocessable:
    print(f"  ! {u}")
