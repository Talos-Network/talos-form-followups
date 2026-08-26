"""Non-secret configuration. Secrets NEVER go in this file (hard rule 1)."""

# The only Slack user whose replies count as instructions (docs/decisions.md #6).
# Slack member IDs are not secrets. Find yours: Slack profile -> ... -> Copy member ID.
APPROVER_SLACK_ID = "U07PLRR8UCT"  # Steve

# Pending drafts older than this many days are flagged in the daily summary.
STALE_PENDING_DAYS = 3

# The sending safety ladder (hard rule 3). Promote one step at a time:
#   "stub"     - no email exists; the poller prints/reports what it would send
#   "self"     - real emails, but every recipient is replaced by APPROVER_EMAIL
#   "live"     - real emails to real people
SEND_MODE = "live"
APPROVER_EMAIL = "stephen@talosnetwork.org"
OPS_FROM = "ops@talosnetwork.org"
