"""The poller (build step 7: INTERPRETATION-ONLY). Reads each Pending draft's
Slack thread, works out what the approver wants, and posts what it WOULD do
back into the thread. Nothing is sent, no ledger state changes — that arrives
in step 8, wired behind these exact same readings.

Approval channels (docs/decisions.md):
- A ✅ (white_check_mark) reaction on the draft message, from the allowlisted
  approver = approve.
- Anything else happens in thread replies, classified conservatively by
  interpretation.classify_reply.
- Thread replies OUTRANK the reaction: if there are new replies, they are
  what gets read; a ✅ alongside a written "skip" never wins.
- Replies and reactions from anyone not on the allowlist are ignored.

Idempotency: the poller only reads human replies newer than its own last
message in each thread, and only announces a reaction once — so a 15-minute
cron re-reads quietly and stays silent unless something new happened.
"""

from __future__ import annotations

import anthropic

from airtable_client import fetch_pending_nudges
from config import APPROVER_SLACK_ID
from interpretation import classify_reply
from slack_client import (parse_permalink, post_message, reaction_users,
                          thread_replies)

APPROVE_EMOJI = "white_check_mark"
APPROVED_MARKER = "Read as *approve*"

INTERPRETATION_ONLY_NOTE = "(Interpretation-only mode: nothing sent, nothing changed.)"


def _respond(interp) -> str:
    if interp.intent == "approve":
        return (f"✅ {APPROVED_MARKER} — in live mode I'd send this email now "
                f"and mark it Sent. {INTERPRETATION_ONLY_NOTE}")
    if interp.intent == "edit":
        return (f"✏️ Read as an *edit request*: _{interp.edit_instructions}_\n"
                f"In live mode I'd revise the draft and post it back here for a "
                f"fresh approval. {INTERPRETATION_ONLY_NOTE}")
    if interp.intent == "reject":
        return (f"🚫 Read as *skip* — in live mode I'd mark this nudge Rejected "
                f"for the month. {INTERPRETATION_ONLY_NOTE}")
    return f"❓ {interp.clarifying_question}\n_(I won't act until it's clear.)_"


def main() -> None:
    pending = fetch_pending_nudges()
    # Batch rows share one thread — process each thread once.
    threads: dict[str, dict] = {}
    for row in pending:
        link = row["fields"].get("Slack thread")
        if link:
            threads.setdefault(link, row)

    client = anthropic.Anthropic()
    acted, checked = 0, 0
    for link, row in threads.items():
        checked += 1
        channel, ts = parse_permalink(link)
        msgs = thread_replies(channel, ts)

        last_bot_index = max(i for i, m in enumerate(msgs) if m.get("bot_id"))
        new_replies = [m for m in msgs[last_bot_index + 1:]
                       if m.get("user") == APPROVER_SLACK_ID and not m.get("bot_id")]

        if new_replies:
            reply_text = "\n".join(m.get("text", "") for m in new_replies)
            interp = classify_reply(client, row["fields"].get("Draft", ""), reply_text)
            post_message(channel, _respond(interp), thread_ts=ts)
            print(f"{row['fields'].get('Nudge', link)}: reply read as {interp.intent}")
            acted += 1
            continue

        # No new words — check for a fresh ✅ from the approver on the draft
        # itself. An edit conversation in the thread voids the reaction path:
        # a revision needs its own approval, never the original message's ✅.
        conversation_started = len(msgs) > 1
        already_announced = any(APPROVED_MARKER in m.get("text", "")
                                for m in msgs if m.get("bot_id"))
        if (not conversation_started and not already_announced
                and APPROVER_SLACK_ID in reaction_users(channel, ts, APPROVE_EMOJI)):
            post_message(channel, (
                f"✅ {APPROVED_MARKER} (via reaction) — in live mode I'd send this "
                f"email now and mark it Sent. {INTERPRETATION_ONLY_NOTE}"), thread_ts=ts)
            print(f"{row['fields'].get('Nudge', link)}: ✅ reaction read as approve")
            acted += 1

    print(f"Checked {checked} pending thread(s); responded to {acted}.")


if __name__ == "__main__":
    main()
