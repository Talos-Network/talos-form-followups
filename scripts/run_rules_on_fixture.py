"""Run the rules engine over the local fixture.json and print what it would do.

Read-only, no network, no history (an empty Nudges ledger). For hand-verifying
the engine against real people. Usage: python3 scripts/run_rules_on_fixture.py
"""

import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from rules import who_needs_nudging  # noqa: E402

fixture = json.loads((Path(__file__).resolve().parent.parent / "fixture.json").read_text())
today = date.today()
result = who_needs_nudging(fixture["placements"], history=[], today=today)

print(f"Rules run over fixture ({len(fixture['placements'])} placements), today = {today}\n")
print(f"DUE ({len(result.due)}):")
for n in result.due:
    cc = f", CC {n.supervisor_email}" if n.cc_supervisor else ""
    print(f"  - {n.recipient} nudge, rung {n.rung}, depth {n.depth}: "
          f"{n.first_name} <{n.email}> re {n.org}{cc}\n      {n.reason}")
print(f"\nSILENCED (paused/completed): {result.silenced or 'none'}")
print(f"\nUNPROCESSABLE (a human should look):")
for u in result.unprocessable or ["none"]:
    print(f"  - {u}")
print(f"\nQUIET (checked, nothing due):")
for q in result.quiet or ["none"]:
    print(f"  - {q}")
