"""Draft today's nudges and write them to drafts/ (gitignored). NO sending,
NO Airtable writes, NO Slack — pure preview for iterating on the voice.
Usage: python3 scripts/preview_drafts.py  (needs AIRTABLE_TOKEN + ANTHROPIC_API_KEY)
"""

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import anthropic  # noqa: E402

from airtable_client import fetch_nudge_history, fetch_placements  # noqa: E402
from drafting import draft_fellow_nudge, draft_supervisor_batch  # noqa: E402
from rules import consolidate_supervisor_nudges, who_needs_nudging  # noqa: E402

today = date.today()
result = who_needs_nudging(fetch_placements(), fetch_nudge_history(), today)
fellows, batches = consolidate_supervisor_nudges(result.due, result.supervisor_context)
print(f"{len(fellows)} fellow nudge(s), {len(batches)} supervisor email(s) to draft.\n")

client = anthropic.Anthropic()
out = [f"# Draft preview — {today}\n"]
for n in fellows:
    label = f"FELLOW {n.first_name} ({n.org}) — rung {n.rung}, depth {n.depth}" + (
        f", CC {n.supervisor_email}" if n.cc_supervisor else "")
    print(f"drafting: {label}")
    try:
        subject, body = draft_fellow_nudge(client, n)
        out.append(f"\n## {label}\nTo: {n.email}\nSubject: {subject}\n\n{body}\n")
    except Exception as e:  # surface, keep drafting the rest
        out.append(f"\n## {label}\nFAILED: {e}\n")
for b in batches:
    label = (f"SUPERVISOR {b.first_name} <{b.email}> — rung {b.rung}, "
             f"{len(b.items)} due, {len(b.also_outstanding)} also-outstanding")
    print(f"drafting: {label}")
    try:
        subject, body = draft_supervisor_batch(client, b)
        out.append(f"\n## {label}\nTo: {b.email}\nSubject: {subject}\n\n{body}\n")
    except Exception as e:
        out.append(f"\n## {label}\nFAILED: {e}\n")

dest = Path(__file__).resolve().parent.parent / "drafts"
dest.mkdir(exist_ok=True)
path = dest / f"{today}.md"
path.write_text("".join(out))
print(f"\nWrote {path}")
