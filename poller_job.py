"""The poller (every 15 min): reads each Pending draft's Slack thread, works
out what the approver wants, and ACTS:

  approve -> send the email (per config.SEND_MODE's safety ladder), stamp the
             ledger row(s) Sent, confirm in-thread
  edit    -> revise the draft, update the ledger, post the revision for a
             FRESH approval (never sent on the old approval's strength)
  skip    -> stamp Rejected (silences that person for the month), confirm
  unclear -> ask one polite question; never act

Approval channels (docs/decisions.md #6b): a ✅ reaction from the allowlisted
approver on the draft message, or on the latest posted revision — or a clear
written approval in the thread. Thread replies outrank reactions; once a
conversation has started, only the latest revision's ✅ counts.

Double-send protection, layered: only Pending rows are polled at all (a Sent
stamp removes the thread from the next poll); rows are stamped immediately
after the send call returns; and the poller only reads human replies newer
than its own last message in each thread, so one reply is acted on once.
"""

from __future__ import annotations

from datetime import date

import anthropic

from airtable_client import (fetch_pending_nudges, fetch_recently_sent_nudges,
                             stamp_rejected, stamp_sent, update_draft)
from config import APPROVER_SLACK_ID, SEND_MODE
from drafting import revise_draft, split_draft
from interpretation import classify_reply
from sender import send_email
from slack_client import (parse_permalink, post_message, reaction_users,
                          thread_replies)

APPROVE_EMOJI = "white_check_mark"
REVISION_MARKER = "Here's the revised draft"


def _approve(rows: list[dict], channel: str, ts: str) -> None:
    """Send once per thread (batch rows share one email), stamp every row."""
    fields = rows[0]["fields"]
    to = fields.get("To")
    if not to:
        post_message(channel, ("⚠️ I can't send this one: the ledger row has no "
                               "recipient (it predates the To field). Reply *skip* "
                               "and it will be re-drafted on a future run."), thread_ts=ts)
        return
    subject, body = split_draft(fields.get("Draft", ""))
    outcome = send_email(to, subject, body, cc=fields.get("CC", ""))
    for row in rows:
        stamp_sent(row["id"], APPROVER_SLACK_ID, date.today())
    note = " (ledger marked Sent)" if SEND_MODE != "stub" else \
        " (ledger marked Sent — stub mode, no real email existed)"
    post_message(channel, f"✅ Approved — {outcome}.{note}", thread_ts=ts)
    print(f"{fields.get('Nudge')}: approved -> {outcome}")


def _edit(rows: list[dict], instructions: str, client, channel: str, ts: str) -> None:
    current = rows[0]["fields"].get("Draft", "")
    try:
        subject, body = revise_draft(client, current, instructions)
    except Exception as e:
        post_message(channel, f"⚠️ I couldn't produce a revision: {e}", thread_ts=ts)
        return
    revised = f"Subject: {subject}\n\n{body}"
    for row in rows:
        update_draft(row["id"], revised, previous=current)
    post_message(channel, (
        f"{REVISION_MARKER}:\n\n*Subject:* {subject}\n\n{body}\n\n"
        f"_React ✅ on this message (or reply *approve*) to send it — the "
        f"revision needs its own approval._"), thread_ts=ts)
    print(f"{rows[0]['fields'].get('Nudge')}: revised per edit request")


def _reject(rows: list[dict], channel: str, ts: str) -> None:
    for row in rows:
        stamp_rejected(row["id"], APPROVER_SLACK_ID)
    post_message(channel, ("🚫 Skipped — marked Rejected in the ledger. They "
                           "won't be chased again this month."), thread_ts=ts)
    print(f"{rows[0]['fields'].get('Nudge')}: skipped")


def main() -> None:
    pending = fetch_pending_nudges()
    threads: dict[str, list[dict]] = {}
    for row in pending:
        link = row["fields"].get("Slack thread")
        if link:
            threads.setdefault(link, []).append(row)

    client = anthropic.Anthropic()
    acted = 0
    for link, rows in threads.items():
        channel, ts = parse_permalink(link)
        msgs = thread_replies(channel, ts)
        last_bot_index = max(i for i, m in enumerate(msgs) if m.get("bot_id"))
        new_replies = [m for m in msgs[last_bot_index + 1:]
                       if m.get("user") == APPROVER_SLACK_ID and not m.get("bot_id")]

        if new_replies:
            reply_text = "\n".join(m.get("text", "") for m in new_replies)
            interp = classify_reply(client, rows[0]["fields"].get("Draft", ""), reply_text)
            if interp.intent == "approve":
                _approve(rows, channel, ts)
            elif interp.intent == "edit":
                _edit(rows, interp.edit_instructions, client, channel, ts)
            elif interp.intent == "reject":
                _reject(rows, channel, ts)
            else:
                post_message(channel, f"❓ {interp.clarifying_question}\n"
                                      f"_(I won't act until it's clear.)_", thread_ts=ts)
                print(f"{rows[0]['fields'].get('Nudge')}: unclear, asked")
            acted += 1
            continue

        # No new words — check reactions. The ✅ target is the original draft
        # message while the thread is untouched, or the LATEST revision once
        # a conversation exists. Reactions on anything else don't count.
        revision_ts = next((m["ts"] for m in reversed(msgs)
                            if m.get("bot_id") and REVISION_MARKER in m.get("text", "")), None)
        conversation_started = len(msgs) > 1
        target_ts = revision_ts if revision_ts else (None if conversation_started else ts)
        if target_ts and APPROVER_SLACK_ID in reaction_users(channel, target_ts, APPROVE_EMOJI):
            _approve(rows, channel, ts)
            acted += 1

    # Closed threads aren't acted on, but they shouldn't be silent either: a
    # reply on a recently-Sent nudge gets one acknowledgment saying where
    # that kind of message actually goes. Same idempotency as everywhere
    # else — only replies newer than the bot's own last message are seen.
    closed_acks = 0
    seen = set(threads)
    for row in fetch_recently_sent_nudges():
        link = row["fields"].get("Slack thread")
        if not link or link in seen:
            continue
        seen.add(link)
        channel, ts = parse_permalink(link)
        msgs = thread_replies(channel, ts)
        last_bot_index = max(i for i, m in enumerate(msgs) if m.get("bot_id"))
        new_replies = [m for m in msgs[last_bot_index + 1:]
                       if m.get("user") == APPROVER_SLACK_ID and not m.get("bot_id")]
        if new_replies:
            post_message(channel, (
                "This email already went out, so I don't act on replies in this "
                "thread. If that was tone or wording feedback, take it to Claude — "
                "the drafting prompt lives in the talos-form-followups repo and "
                "your note is exactly what improves it. If this person needs a "
                "correction or follow-up email, that's a manual send from ops@."),
                thread_ts=ts)
            print(f"{row['fields'].get('Nudge')}: acknowledged reply on closed thread")
            closed_acks += 1

    print(f"Checked {len(threads)} pending thread(s); acted on {acted}; "
          f"acknowledged {closed_acks} closed-thread repl(ies). SEND_MODE={SEND_MODE}")


if __name__ == "__main__":
    main()
