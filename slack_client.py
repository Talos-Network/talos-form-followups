"""Slack I/O. Trial surface: a DM with the approver (docs/decisions.md #4).
The bot token comes from SLACK_BOT_TOKEN; it is never printed or logged."""

from __future__ import annotations

import json
import os
import sys
import urllib.parse
import urllib.request


def _token() -> str:
    token = os.environ.get("SLACK_BOT_TOKEN")
    if not token:
        sys.exit("SLACK_BOT_TOKEN is not set.")
    return token


def _check(method: str, body: dict) -> dict:
    if not body.get("ok"):
        sys.exit(f"Slack {method} failed: {body.get('error')}")
    return body


def _call(method: str, payload: dict) -> dict:
    """POST methods (chat.postMessage, conversations.open) take JSON."""
    req = urllib.request.Request(
        f"https://slack.com/api/{method}",
        data=json.dumps(payload).encode(),
        headers={"Authorization": f"Bearer {_token()}",
                 "Content-Type": "application/json; charset=utf-8"})
    with urllib.request.urlopen(req) as resp:
        return _check(method, json.load(resp))


def _get(method: str, params: dict) -> dict:
    """GET methods (chat.getPermalink, conversations.replies) take a query
    string — they reject JSON bodies with invalid_arguments."""
    url = f"https://slack.com/api/{method}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {_token()}"})
    with urllib.request.urlopen(req) as resp:
        return _check(method, json.load(resp))


def open_dm(user_id: str) -> str:
    """Channel id of the bot's DM with this user (idempotent)."""
    return _call("conversations.open", {"users": user_id})["channel"]["id"]


def post_message(channel: str, text: str, thread_ts: str | None = None) -> str:
    payload = {"channel": channel, "text": text}
    if thread_ts:
        payload["thread_ts"] = thread_ts
    return _call("chat.postMessage", payload)["ts"]


def permalink(channel: str, ts: str) -> str:
    return _get("chat.getPermalink", {"channel": channel, "message_ts": ts})["permalink"]
