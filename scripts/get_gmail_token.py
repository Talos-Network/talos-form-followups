"""One-time OAuth flow: obtain the Gmail refresh token for the sending
account and store it DIRECTLY in the macOS Keychain — it is never printed,
logged, or written to a file (hard rule 1).

Needs GMAIL_CLIENT_ID and GMAIL_CLIENT_SECRET in the environment (ffsecrets).
Scope requested: gmail.send only — this credential can send email and do
nothing else; it cannot read anyone's inbox.

Usage: python3 scripts/get_gmail_token.py
A browser opens; sign in as the account that sends from ops@, approve, done.
"""

import http.server
import json
import os
import subprocess
import sys
import urllib.parse
import urllib.request
import webbrowser

PORT = 8765
REDIRECT = f"http://localhost:{PORT}"
SCOPE = "https://www.googleapis.com/auth/gmail.send"
KEYCHAIN_ITEM = "talos-form-followups.gmail-refresh"

client_id = os.environ.get("GMAIL_CLIENT_ID")
client_secret = os.environ.get("GMAIL_CLIENT_SECRET")
if not (client_id and client_secret):
    sys.exit("GMAIL_CLIENT_ID / GMAIL_CLIENT_SECRET not set — run ffsecrets first.")

auth_url = "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode({
    "client_id": client_id, "redirect_uri": REDIRECT, "response_type": "code",
    "scope": SCOPE, "access_type": "offline", "prompt": "consent",
})

result: dict = {}


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        result["code"] = query.get("code", [""])[0]
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(b"<h2>Done \xe2\x80\x94 close this tab and return to the terminal.</h2>")

    def log_message(self, *args):  # keep the auth code out of terminal logs
        pass


print("Opening your browser. Sign in as the account that sends from ops@, and approve.")
webbrowser.open(auth_url)
with http.server.HTTPServer(("localhost", PORT), Handler) as server:
    while "code" not in result:
        server.handle_request()
if not result["code"]:
    sys.exit("No authorisation code came back — re-run and approve the consent screen.")

req = urllib.request.Request(
    "https://oauth2.googleapis.com/token",
    data=urllib.parse.urlencode({
        "code": result["code"], "client_id": client_id,
        "client_secret": client_secret, "redirect_uri": REDIRECT,
        "grant_type": "authorization_code",
    }).encode())
try:
    with urllib.request.urlopen(req) as resp:
        tokens = json.load(resp)
except urllib.error.HTTPError as e:
    sys.exit(f"Token exchange failed: HTTP {e.code}")

refresh = tokens.get("refresh_token")
if not refresh:
    sys.exit("Google returned no refresh token — re-run (the prompt=consent flow "
             "should always include one; if it persists, revoke the app's access "
             "at myaccount.google.com/permissions and try again).")

subprocess.run(["security", "add-generic-password", "-U", "-a", os.environ["USER"],
                "-s", KEYCHAIN_ITEM, "-w", refresh], check=True)
print("Refresh token stored in Keychain (never displayed). Run `ffsecrets` in new "
      "terminals to load it.")
