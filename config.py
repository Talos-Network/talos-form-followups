"""Non-secret configuration. Secrets NEVER go in this file (hard rule 1)."""

# The only Slack user whose replies count as instructions (docs/decisions.md #6).
# Slack member IDs are not secrets. Find yours: Slack profile -> ... -> Copy member ID.
APPROVER_SLACK_ID = "U07PLRR8UCT"  # Steve

# Pending drafts older than this many days are flagged in the daily summary.
STALE_PENDING_DAYS = 3
