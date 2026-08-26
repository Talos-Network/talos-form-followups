"""Email sending via the Gmail API (raw REST, no extra dependencies), gated
by config.SEND_MODE:

  stub  -> nothing is sent; returns a description (development default)
  self  -> a real email is sent, but every recipient is replaced by
           config.APPROVER_EMAIL and the CC dropped (first-sends + rehearsal)
  live  -> real recipients

Credentials (only needed for self/live): GMAIL_CLIENT_ID, GMAIL_CLIENT_SECRET,
GMAIL_REFRESH_TOKEN in the environment — the OAuth setup walkthrough covers
where these come from. Secrets never appear in output (hard rule 1).
"""

from __future__ import annotations

import base64
import json
import os
import sys
import urllib.parse
import urllib.request
from email.message import EmailMessage

from config import APPROVER_EMAIL, OPS_FROM, SEND_MODE


def _access_token() -> str:
    client_id = os.environ.get("GMAIL_CLIENT_ID")
    client_secret = os.environ.get("GMAIL_CLIENT_SECRET")
    refresh_token = os.environ.get("GMAIL_REFRESH_TOKEN")
    if not all((client_id, client_secret, refresh_token)):
        sys.exit("Gmail credentials not set (GMAIL_CLIENT_ID / _SECRET / _REFRESH_TOKEN).")
    req = urllib.request.Request(
        "https://oauth2.googleapis.com/token",
        data=urllib.parse.urlencode({
            "client_id": client_id, "client_secret": client_secret,
            "refresh_token": refresh_token, "grant_type": "refresh_token",
        }).encode())
    try:
        with urllib.request.urlopen(req) as resp:
            return json.load(resp)["access_token"]
    except urllib.error.HTTPError as e:
        sys.exit(f"Gmail token refresh failed: HTTP {e.code}")


def _gmail_send(to: str, subject: str, body: str, cc: str = "") -> None:
    msg = EmailMessage()
    msg["From"] = OPS_FROM
    msg["To"] = to
    if cc:
        msg["Cc"] = cc
    msg["Subject"] = subject
    msg.set_content(body)
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    req = urllib.request.Request(
        "https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
        data=json.dumps({"raw": raw}).encode(),
        headers={"Authorization": f"Bearer {_access_token()}",
                 "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req) as resp:
            json.load(resp)
    except urllib.error.HTTPError as e:
        sys.exit(f"Gmail send failed: HTTP {e.code}")


def send_email(to: str, subject: str, body: str, cc: str = "") -> str:
    """Sends per SEND_MODE. Returns a human description for the Slack thread."""
    if SEND_MODE == "stub":
        print(f"[stub] would send to {to}" + (f" (cc {cc})" if cc else "")
              + f": {subject}")
        return (f"SEND STUBBED — would have gone to {to}"
                + (f" (CC {cc})" if cc else ""))
    if SEND_MODE == "self":
        _gmail_send(APPROVER_EMAIL, f"[REDIRECTED to you; real: {to}] {subject}", body)
        return (f"sent to {APPROVER_EMAIL} (redirect mode — real recipient "
                f"would be {to}" + (f", CC {cc}" if cc else "") + ")")
    if SEND_MODE == "live":
        _gmail_send(to, subject, body, cc)
        return f"sent to {to}" + (f", CC {cc}" if cc else "")
    sys.exit(f"Unknown SEND_MODE {SEND_MODE!r}")
