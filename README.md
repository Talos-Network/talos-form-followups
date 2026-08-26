# talos-form-followups

Chases overdue monthly progress reports from Talos fellows and their
supervisors. A rules engine decides WHO gets chased and WHEN; Claude drafts
WHAT the email says; a HUMAN approves every send from Slack. Nothing is ever
emailed without a clear per-draft approval from an allowlisted person.

This README is the runbook. It assumes you have never seen the project
before. Design history and every decision's reasoning: `docs/decisions.md`.
What every Airtable field actually means: `docs/data-dictionary.md`.

## How it runs

Two GitHub Actions workflows (Actions tab of this repo):

| Workflow | Schedule | What it does |
|---|---|---|
| `draft` | daily 06:00 UTC (08:00 Berlin summer) + manual button | Reads the Airtable base, applies the ladder rules, drafts nudge emails with Claude, writes each as a `Pending` row in the Nudges table, posts each draft to the approver's Slack DM |
| `poller` | every 15 min + manual button | Reads replies/reactions in each Pending draft's Slack thread and acts: approve → send from ops@ + stamp `Sent`; edit request → revise and repost for fresh approval; skip → stamp `Rejected`; unclear → ask |

No machine other than GitHub's runners is involved. Nobody's laptop matters.

### Approving from Slack (the day-to-day)

Drafts arrive as DMs from the **Placement Form Follow-Up Bot**. For each:

- **✅ reaction** on the draft message = approve and send.
- **Reply in the thread** for anything else: "approve", "make it warmer and
  mention the deadline", "skip — she's on leave this month", a question.
- An edit request gets a revised draft posted back **which needs its own
  approval** (✅ on the revision message, or reply "approve").
- Ambiguous replies get a clarifying question, never an action. Silence
  leaves a draft `Pending` forever — silence is never consent.
- Only replies/reactions from the allowlisted Slack user count (see
  Configuration). Everyone else is ignored.

Approved emails send within ~15 minutes. To hurry one: Actions → poller →
Run workflow.

## Pause / resume (the kill switch)

Actions tab → select the workflow → **⋯ menu → Disable workflow**. Disable
BOTH to stop the machine entirely: no drafts, no polling, nothing can send.
Re-enable the same way. Notes:

- Airtable's own monthly form-request automations are separate and keep
  running — pausing this tool pauses only the chasing.
- Don't reply approvals in Slack while paused: the poller acts on unread
  replies whenever it wakes, even days later.
- Before a planned pause, action every open draft (approve or skip) so
  nothing sits `Pending` and stale.

## Where everything lives

| Thing | Location |
|---|---|
| The data | Airtable base **Placements - MEL** (`appPaWOTEPjPt0BVc`), read through the **Current Placements** view — editing that view's filter changes who gets chased |
| The ledger | **Nudges** table in the same base (`tblHbHOy8GG3cV6JS`) — every draft, approval, rejection, revision and send, forever. The ONLY thing this tool ever writes to Airtable, enforced by a tripwire in `airtable_client.py` |
| The approval surface | Slack DM with the approver, via the **Placement Form Follow-Up Bot** Slack app (api.slack.com/apps) |
| Sending identity | ops@talosnetwork.org via the Gmail API |
| Cloud project | Google Cloud project under the talosnetwork.org organisation (OAuth consent: Internal — this is why the refresh token never expires) |
| Claude API | Anthropic Console, Talos Network org, `form-followups` workspace (spend limit + isolated usage reporting) |
| Secrets | This repo's Actions secrets (Settings → Secrets and variables → Actions). Nowhere else — never in files or commits |

## Credentials and rotation

Six Actions secrets. To rotate any of them: obtain the new value, then from a
Mac with the `gh` CLI: `<command that prints the value> | gh secret set NAME
-R Talos-Network/talos-form-followups` (piping means the value never appears
on screen). All six are held for local development in the macOS Keychain
under `talos-form-followups.*` names, loaded by the `ffsecrets` shell helper.

| Secret | What it is | How to rotate |
|---|---|---|
| `AIRTABLE_TOKEN` | Personal access token scoped to the one base; read everywhere + `data.records:write` (used only on Nudges) | airtable.com/create/tokens → the token → Regenerate |
| `ANTHROPIC_API_KEY` | Key in the `form-followups` workspace | console.anthropic.com → API Keys → delete + create |
| `SLACK_BOT_TOKEN` | Bot token, scopes: `chat:write`, `im:write`, `im:history`, `reactions:read` | api.slack.com/apps → the app → OAuth & Permissions (reinstall after scope changes) |
| `GMAIL_CLIENT_ID` / `GMAIL_CLIENT_SECRET` | OAuth Desktop client in the Cloud project | Cloud console → Clients |
| `GMAIL_REFRESH_TOKEN` | Send-only (`gmail.send`) token for the ops@ sender | run `python3 scripts/get_gmail_token.py` locally (needs the client pair in env), sign in as the ops@ sender |

## Configuration (all non-secret, all in git)

- `config.py` — the approver's Slack member ID (the allowlist), the
  `SEND_MODE` safety ladder (`stub` → `self` → `live`), stale-pending
  threshold, ops sender address.
- `rules.py` top block — the ladder: rung day thresholds (7/14/21), max
  nudges per month (3), supervisor-CC depth (3), minimum days between
  nudges (6), the 10-day pre-request grace window.
- `drafting.py` `VOICE` — the entire voice of the emails: registers per
  rung/depth, Talos house style, banned words. Edit this to change how
  emails read; preview with `scripts/preview_drafts.py` before committing.
- `interpretation.py` `RULES` — how conservatively Slack replies are read.

Changing the approver: new person's Slack member ID (their profile → ⋯ →
Copy member ID) into `config.py`, commit, push. Moving from DM to a private
channel: invite the bot to the channel, then in `draft_job.py` replace
`open_dm(APPROVER_SLACK_ID)` with the channel's ID (right-click the channel
→ copy link — the ID is the C… segment).

## Local development

Secrets load from the Keychain: `ffsecrets` (defined in `~/.zshrc`).

- `python3 -m unittest discover -s tests -t .` — the rules test suite.
- `python3 draft_job.py --dry-run` — fixture-driven, zero network, cannot
  send, write, or post. `fixture.json` is real fellows' data: gitignored,
  never commit it (`git status` before every commit).
- `python3 scripts/preview_drafts.py` — drafts today's real due list to
  `drafts/<date>.txt` (gitignored). Reads live Airtable, sends nothing.
- `python3 scripts/pull_fixture.py` — refresh the fixture (whitelisted
  fields only; the qualitative form answers are never fetched).

## Safety properties (what cannot happen)

- Nothing sends without a clear approval from the allowlisted human;
  unclear replies produce questions; silence produces nothing.
- Nothing sends twice: only `Pending` rows are polled, rows are stamped on
  send, and the poller only reads replies newer than its own last message.
- A revised draft is never sent on the original approval.
- Paused and completed placements are never chased (checked in code, not
  just the view); records missing a Start Date are surfaced to a human, not
  guessed at.
- Fellows' qualitative form answers never enter a prompt, a draft, or this
  repo. The drafting model sees metadata only.
- The Airtable token physically can't be scoped to one table, so every
  write in this codebase routes through one function that refuses any table
  except Nudges.

## Known limits / v2 parking lot

- Pauses have no date range in the base, so a returning fellow's depth
  counts the paused months (their first email back may read heavier than
  deserved, and can trigger the supervisor CC) — the human approval is the
  backstop; eyeball freshly-unpaused people.
- Replies from fellows to the nudge emails are not detected (v2).
- Auto-send for rung-1 nudges: only after ≥2 clean months, 20+ ledger rows,
  zero targeting errors and ≥95% unedited approvals — the ledger itself is
  the evidence base for that decision.
- The Anthropic Console org has a single admin; add a second.
