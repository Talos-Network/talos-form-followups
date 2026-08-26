# CLAUDE.md — talos-form-followups

Instructions for Claude Code sessions maintaining this tool. The original
build brief this replaced is in git history (first commit); the tool was
built and went live in August 2026.

## What this is

Chases overdue monthly progress reports from Talos fellows and supervisors.
Deterministic rules decide WHO and WHEN (`rules.py`, unit-tested, no AI);
Claude drafts WHAT (`drafting.py` — the `VOICE` block is the programme's
voice); a human approves every send from Slack (`poller_job.py`, conservative
reply interpretation). Two GitHub Actions workflows run it; nothing depends
on anyone's machine.

Read before changing anything: `README.md` (the runbook — operations,
credentials, rotation, pause/resume), `docs/decisions.md` (every design
decision and why), `docs/data-dictionary.md` (what each Airtable field
actually means, verified against real records — several field names are
traps, all documented there).

## Hard rules (as binding as ever)

1. **Secrets** live only in GitHub Actions secrets and, locally, the macOS
   Keychain loaded via the `ffsecrets` shell helper. Never in files,
   commits, logs, echoes, or error messages — error handlers print status
   codes only.
2. **fixture.json is real fellows' data**: gitignored, never committed.
   Check `git status` before every commit.
3. **Nothing sends without a clear per-draft approval** from the allowlisted
   Slack user; nothing sends twice; unclear replies produce questions, never
   sends; a revision always needs a fresh approval. No send-all shortcut
   exists and none may be added.
4. **No qualitative form content** (the What went well? answers, ratings)
   may ever enter a prompt, a draft, an email, or this repo. Drafting sees
   metadata only; the Airtable field whitelists enforce this — keep them.
5. **Paused, completed, and no-start-date placements are never chased.**
   Checked in code, not just the Airtable view. This is the failure mode
   that damages trust in the programme.
6. Emails are from "Talos Ops" — never Steve's personal voice.
7. **The single-table write tripwire in `airtable_client.py` stays**: every
   Airtable write routes through `_write()`, which refuses any table except
   Nudges. The token cannot be scoped to one table, so this code is the
   guarantee.

## Working with Steve

This is a learning project as much as a tool. Walk him through every step
with complete, runnable instructions (one command per block); explain what
things do briefly and in plain language as you go; answer "why" properly
when he asks. Do not quiz him or pepper the work with check-in questions.
Only stop for genuine decisions that are his to make — tone, thresholds,
anything fellows or supervisors experience. When a confusion gets resolved,
say "friction log entry" — he keeps one and blogs.

## Map

| File | Role |
|---|---|
| `rules.py` | The ladder, silencers, grace windows, consolidation. Config constants at the top. All logic changes need tests in `tests/` |
| `drafting.py` | The Claude drafting call and `VOICE` — iterate on tone here, preview with `scripts/preview_drafts.py` |
| `interpretation.py` | Conservative classification of approver replies |
| `airtable_client.py` | All Airtable I/O; the write tripwire; field whitelists |
| `slack_client.py` / `sender.py` | Slack and Gmail plumbing (`SEND_MODE` ladder in `config.py`) |
| `draft_job.py` / `poller_job.py` | The two entry points the workflows run |

Before any change that depends on the Airtable schema, re-verify against the
live base — field names have changed before and will again.
