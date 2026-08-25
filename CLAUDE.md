# CLAUDE.md — talos-form-followups

Instructions for Claude Code. Read fully before doing anything.

## What this project is

A tool that reviews fellow and supervisor progress-form completion in Airtable, drafts personalised chase-up emails for the ones who are behind, and — after Steve approves each draft interactively — sends them from ops@talosnetwork.org.

**v1 runs in the cloud (GitHub Actions) with Airtable as the approval surface — no dependency on Steve's Mac or on Steve personally.** Two jobs:

1. **Draft job** (weekly cron + workflow_dispatch): reads form status, applies the rules, drafts nudges, writes each to the Nudges table with status `Pending`, and posts each draft as its own message in a private Slack channel (#form-nudges) — recipient, rung, reason, draft text — plus a one-screen summary.
2. **Poller job** (Actions cron every ~15–30 min, plus dispatch): reads replies in each draft's Slack thread, interprets them with a Claude call, and acts: approve → send from ops@ via Gmail API, stamp `Sent`; edit request → revise the draft, post the revision back to the thread for a fresh approval; skip → stamp `Rejected`. It always confirms what it did back in the thread.

**The approval surface is a Slack conversation** — Steve (or a successor) replies to the bot in plain language, like messaging a team member: "approve", "approve but warmer", "skip — she's on leave this month". Airtable's Nudges table remains the ledger underneath: every state change is recorded there, so the interface could be rebuilt without losing history. Inbound replies FROM fellows (to the nudge emails themselves) remain v2, out of scope.

### Reply-interpretation guardrails (hard requirements)

- Only replies from an **allowlisted set of human Slack user IDs** are read as instructions. Bot messages, reactions from others, and anyone off the list are ignored.
- Interpretation is **conservative by construction**: the Claude call classifies each reply as approve / edit-request / reject / unclear, and anything unclear (or anything that mixes approval with conditions the bot can't verify) is treated as NOT approved — the bot asks a clarifying question in the thread instead. It never guesses its way to a send.
- An edited draft is never sent on the strength of the original approval — revision posts back to the thread and waits for a fresh "approve".
- A thread with no reply stays `Pending` forever. Silence is never consent. The next draft-job run may re-surface stale pending items in its summary.

## Continuity requirement — this tool must survive Steve leaving

- Repo lives in (or moves to) the **Talos GitHub org**, not a personal account, before real credentials are added.
- All credentials belong to the organisation: the Google Cloud project under the Talos Workspace, OAuth for the ops@ mailbox (consent screen **Internal** — external/testing-mode refresh tokens expire in 7 days), Airtable token created against a role-appropriate account rather than tied to Steve where feasible.
- The README is a runbook: what it does, when it runs, where each credential lives and how to rotate it, how to pause it (disable the workflow), and how to change the ladder. Written for a successor who has never seen this chat.

## Who you're working with

Steve is upskilling and this is a learning project as much as a tool — but the contract has changed since talos-leave-bot: **walk him through every step with complete instructions; do NOT quiz him, do not ask him to paraphrase, do not pepper the work with check-in questions.** Explain what things do as you go (briefly, in plain language) and answer "why" properly when he asks — he learns by doing and reading, not by being tested. Only stop for genuine decisions that are his to make. Never give half-instructions: every step should be runnable as given.

This is Steve's second build. Assume the leave-bot lessons are learned (repo/secrets/fixtures) — don't re-teach them. He keeps a friction log and blogs — say "friction log entry" when a confusion gets resolved.

## Architecture: deterministic core, judgment layer

- **Rules decide WHO and WHEN** (plain Python, unit-tested, no AI): who's behind, how far, whether they were nudged recently, whether to escalate.
- **Claude drafts WHAT** (one Anthropic API call per nudge): tone varies by rung — first nudge gentle, later ones firmer, supervisor chases professional. The model never decides whether to contact someone.
- **A human decides SEND** (v1: an explicit per-draft approval reply in the Slack thread, interpreted conservatively; the poller sends only clearly-approved, not-yet-sent drafts. Drafting never sends; a human reply sits between the two by construction).

## Ground truth: the Airtable base (verified 25 Aug 2026 — re-verify schema before coding)

Base: **Placements - MEL** (`appPaWOTEPjPt0BVc`). Read it via the Airtable API with a **personal access token scoped to this one base, read-only** — do not accept a broader token; explain least-privilege to Steve when he creates it (contrast with the admin-level Timetastic key).

Key tables/fields (names as of today — confirm against the live schema, they may have changed):

- **Placements** (`tblPat6wJi9lYNOAt`) — one row per fellow placement. The deterministic "who's behind" logic ALREADY EXISTS here as formulas — read it, don't reimplement:
  - `Expected Reports`, `Actual Reports (Fellows)`, `Status (Fellows)`, `Updates? (Fellows)` — and the parallel `(Supervisors)` fields
  - `Placement Paused?` (checkbox) and `Placement Completed` — **anyone paused or completed is never chased**
  - `Fellow Email`, `First Name`, `Fellow Form Link`, `Supervisor Form Link`, supervisor name/email via lookups, `Cohort`, `Start Date`/`End Date`, `Last Form Completed`
- **Supervisors** (`tblKk37FAdsFuRwHW`) — supervisor contact info, days/weeks since last form.
- **Fellows Forms** / **Supervisors Forms** — the submissions themselves. **The rich-text answers (What went well? etc.) are sensitive qualitative feedback. Never put their contents into a nudge email or a Claude prompt.** The drafting prompt gets metadata only: name, role, how many forms behind, days since last submission, the form link, nudge history.

With Steve, first session: pull 3–4 real Placements records as `fixture.json` (gitignored), read them together, and confirm what each Status/Updates formula actually means — including edge cases (what does `Status` show before the first report is due? what if `Expected Reports` is 0?). Write the answers as a data dictionary at the top of the main script.

## The missing piece: nudge memory

The base has NO record of reminders sent. Without it there is no ladder and no restraint. Propose to Steve a new **Nudges** table in the same base (fields roughly: link to Placement, who was contacted (fellow/supervisor), rung (1/2/3), date, draft used, approved-and-sent? — final shape is his call). The tool writes a row per approved nudge; the rules read it. This is the ONLY thing the tool ever writes to Airtable, and only after Steve approves a draft. Alternative designs (a local state file, a separate base) exist — present the trade-offs once, let him choose. Note the token must then allow writes to that one table.

## Hard rules

1. **Secrets:** `AIRTABLE_TOKEN` (scoped as above), `ANTHROPIC_API_KEY`, and the Gmail OAuth credentials live only in GitHub Actions secrets and, locally during development, env vars set via `read -s`. Never in files, commits, logs, echoes, or error messages.
2. **fixture.json is gitignored before it exists.** It contains real fellows' data. Check `git status` before every commit.
3. **Nothing sends without a clear per-draft approval from an allowlisted human in the Slack thread** (per the guardrails above). The poller must never draft, auto-approve, or send anything twice (check Sent state in Airtable before sending; stamp immediately after). No send-all shortcut. During development, sending is stubbed to print; the first real sends go to Steve's own address; then a full rehearsal run with every recipient redirected to Steve; only then real people.
4. **Slack credentials:** the bot token is scoped to the one private channel (read + write); it is a secret like the others.
5. **No qualitative form content in prompts or drafts** (see above).
6. **Respect `Placement Paused?` and ended placements unconditionally.** A paused fellow receiving a chase email is the failure mode that damages trust in the whole programme.
7. Emails are drafted as from the Talos ops team and transparently assistant-written where relevant — never impersonating Steve's personal voice.

## Design decisions to interview Steve on BEFORE coding (one at a time)

1. The nudge ladder: what counts as "behind enough" for rung 1? Days between rungs? When does a fellow's lateness escalate to their supervisor being told, if ever? (Chasing supervisors about their OWN forms is separate from telling supervisors about their fellow's lateness — clarify both.)
2. Tone per rung, and the sign-off identity.
3. Nudges table shape (see above).
4. Run cadence (weekly? aligned to which day?) and where the summary goes (Slack channel via webhook — reuse the leave-bot pattern — or just the drafts file for now).
5. Nudges table shape (the ledger): status (`Pending`/`Approved`/`Rejected`/`Sent`), draft text + revisions, Slack thread reference, who approved, timestamps.
6. The allowlist: which Slack users' replies count as instructions (start: Steve only).
7. Poller cadence (15 vs 30 min) and the Slack channel name/membership.
8. Anything that should pause chasing beyond the checkbox (e.g. cohort breaks, known leave).
9. Walk Steve through BOTH credential setups completely, no gaps: the Slack app (bot token, channel scopes) and the Google Cloud/OAuth setup (project under the Talos Workspace, consent screen Internal, credentials, refresh token, into Actions secrets) — the fiddliest credential work he'll have done.

## Build order

1. Housekeeping: repo, `.gitignore` (fixture.json, `__pycache__`, `.env`, drafts output), first push.
2. Fixture + data dictionary (with Steve, as above).
3. Rules engine against the fixture: `who_needs_nudging(records, nudge_history) -> list of (person, role, rung, reason)`. Unit tests — including paused, completed, brand-new placement, supervisor-of-many-fellows. Steve verifies output by hand against the fixture.
4. Nudges table created; reading it in the rules engine; writing a row on each approved send.
5. Drafting: one Claude API call per nudge (metadata-only prompt, per hard rule 4). Show Steve the prompt itself and iterate on tone with him — the prompt is where the programme's voice lives.
6. Draft job end-to-end locally: rules → drafts → Pending rows in Nudges → draft messages + summary into the private Slack channel. Iterate with Steve on how drafts read in Slack.
7. Poller, interpretation only: reads threads, classifies replies (approve/edit/reject/unclear), posts what it WOULD do back into the thread — no sending wired yet. Steve converses with it for a few rounds; tune the conservatism until misreads are nil and unclear-handling feels polite.
8. Gmail API setup (full walkthrough per interview item 9); wire real sending into the poller — first real sends to Steve's own address, then a rehearsal cycle with every recipient redirected to Steve, run entirely from Slack approvals.
9. `--dry-run` flag: fixture-driven, no Airtable writes, no Slack posts, sending impossible.
10. Both jobs as GitHub Actions workflows (draft: weekly cron + dispatch; poller: frequent cron + dispatch), every line annotated. Repo in the Talos org with real secrets set there.
11. First real cycle: draft job fires on schedule, Steve approves from his phone in Slack, emails land, ledger populated, bot confirms in-thread. Debrief: ladder, tone, cadence, interpretation misses.
12. Runbook README written for a successor. Then, only after ≥2 clean cycles: discuss v2 (fellow-reply detection that pauses sequences; auto-send for rung-1 nudges if ever trusted — each its own project).

## Definition of done (v1)

- The draft job runs on schedule with no human and no particular machine involved; a human approves by replying in Slack from anywhere; the poller sends from ops@, logs to the ledger, and confirms in-thread. 5-second summary each draft run.
- Nothing ever sends without a clear approval reply; nothing sends twice; unclear replies always produce a question, never a send. Zero qualitative content leakage. Paused/completed never chased.
- A successor could take this over from the README alone: change a threshold, get added to the allowlist, rotate a credential, pause the whole thing.
