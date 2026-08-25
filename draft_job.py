"""The draft job (daily 08:00 Berlin): rules -> Claude drafts -> Pending rows
in the Nudges ledger -> one Slack DM message per draft + a summary.

This job NEVER sends email. Sending lives in the poller, behind a human
approval reply (hard rule 3). Safe to run repeatedly: existing Pending rows
suppress re-drafting the same person.

Failure ordering, deliberate: ledger row first, then Slack post, then the
permalink patched onto the row. A crash between steps leaves a Pending row
with no thread — suppressed from re-drafting and flagged as stale in the
next summary, never duplicated.
"""

from __future__ import annotations

import sys
from datetime import date, timedelta

import anthropic

from airtable_client import (create_pending_nudge, fetch_nudge_history,
                             fetch_pending_nudges, fetch_placements,
                             set_slack_thread)
from config import APPROVER_SLACK_ID, STALE_PENDING_DAYS
from drafting import draft_fellow_nudge, draft_supervisor_batch
from rules import consolidate_supervisor_nudges, who_needs_nudging
from slack_client import open_dm, permalink, post_message

REPLY_HINT = ("_Reply in this thread: *approve* to send it, describe any "
              "changes you'd like, or *skip* to drop it._")


def main() -> None:
    if APPROVER_SLACK_ID == "FILL_ME_IN":
        sys.exit("Set APPROVER_SLACK_ID in config.py first.")
    today = date.today()

    result = who_needs_nudging(fetch_placements(), fetch_nudge_history(), today)
    fellows, batches = consolidate_supervisor_nudges(result.due, result.supervisor_context)
    channel = open_dm(APPROVER_SLACK_ID)
    client = anthropic.Anthropic()
    posted, failures = 0, []

    for n in fellows:
        try:
            subject, body = draft_fellow_nudge(client, n)
        except Exception as e:
            failures.append(f"fellow {n.first_name}: {e}")
            continue
        record_id = create_pending_nudge(n, f"Subject: {subject}\n\n{body}", today)
        intro = f"Hey — I've drafted a follow-up to {n.first_name} about their progress report."
        if n.cc_supervisor:
            intro += f" Their supervisor {n.supervisor_first_name} ({n.supervisor_email}) will be CC'd."
        ts = post_message(channel, (
            f"{intro}\n\n*Subject:* {subject}\n\n{body}\n\n{REPLY_HINT}"))
        set_slack_thread(record_id, permalink(channel, ts))
        posted += 1

    for b in batches:
        try:
            subject, body = draft_supervisor_batch(client, b)
        except Exception as e:
            failures.append(f"supervisor {b.first_name}: {e}")
            continue
        draft_text = f"Subject: {subject}\n\n{body}"
        record_ids = [create_pending_nudge(item, draft_text, today) for item in b.items]
        firsts = [i.person_name.split()[0] for i in b.items]
        listed = " and ".join(", ".join(firsts).rsplit(", ", 1)) if len(firsts) > 1 else firsts[0]
        intro = (f"Hey — I've drafted a follow-up to {b.first_name} about their "
                 f"progress report{'s' if len(firsts) > 1 else ''} on "
                 f"{listed}'s placement{'s' if len(firsts) > 1 else ''}.")
        ts = post_message(channel, (
            f"{intro}\n\n*Subject:* {subject}\n\n{body}\n\n{REPLY_HINT}"))
        link = permalink(channel, ts)
        for record_id in record_ids:
            set_slack_thread(record_id, link)
        posted += 1

    stale = [r for r in fetch_pending_nudges()
             if r["fields"].get("Created at")
             and date.fromisoformat(r["fields"]["Created at"])
             <= today - timedelta(days=STALE_PENDING_DAYS)]

    lines = [f"*Draft run {today}* — {posted} draft(s) posted, "
             f"{len(result.silenced)} silenced, {len(result.quiet)} quiet."]
    if stale:
        names = ", ".join(r["fields"].get("Nudge", r["id"]) for r in stale)
        lines.append(f":hourglass: {len(stale)} pending draft(s) older than "
                     f"{STALE_PENDING_DAYS} days await a reply: {names}")
    for u in result.unprocessable:
        lines.append(f":warning: unprocessable — {u}")
    for f_ in failures:
        lines.append(f":x: drafting failed — {f_}")
    summary = "\n".join(lines)
    post_message(channel, summary)
    print(summary.replace("*", ""))


if __name__ == "__main__":
    main()
