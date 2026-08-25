# Design decisions

Interviewed and decided with Steve, August 2026. Each numbered item maps to the
interview list in CLAUDE.md. Values here are the spec for the rules engine;
thresholds live in config and are cheap to change after the first real cycle.

## 1. The nudge ladder — DECIDED 25 Aug 2026

Two independent dimensions:

### Urgency (within the current month)

The form request goes out on the month-anniversary of the placement start date
(the "request date"). Counting days since the request date, if the current
month's form is still not completed:

| Days since request | Action  |
|--------------------|---------|
| 7+                 | Nudge 1 |
| 14+                | Nudge 2 |
| 21+                | Nudge 3 |
| after that         | Stop for this month. Next month's cycle picks the person up again, now one form deeper behind. |

Hard cap: 3 nudges per person per month.

### Depth (how far behind)

REVISED 25 Aug 2026: depth = the number of monthly request cycles with no
report since the person's last submission (computed from submission dates),
NOT the base's `Expected − Actual`. Reason: programme policy is that nobody
is ever asked to backfill — one report covers the whole period since their
last — so a covering submission wipes the slate. The base formulas count a
historical gap forever, which would have wrongly kept people in the heavy
register (and wrongly CC'd supervisors) after they'd caught up.

Depth never decides WHETHER to nudge — only how the nudge reads, and whether
the supervisor is copied:

- 1 behind: light touch — a simple reminder.
- 2+ behind: heavier register — acknowledges the pattern.
- **3+ behind: the fellow's supervisor is CC'd on the fellow's nudge email.**
  Depth-triggered (any rung), transparent CC on the same email — not a
  separate note. The fellow sees the CC.

Tone is a function of (week rung, depth). Both numbers go into the drafting
prompt.

### Supervisors

Chased about their own forms on the identical ladder (same rungs, same depth
shading). Supervisor-of-many-fellows: their own-form chase is independent of
any CCs they receive about fellows.

### The critical predicate: "is the current month's form done?"

Two routes, used together:

1. Count route: `Actual Reports` >= `Expected Reports` → current form is in,
   person is untouchable this month.
2. Date route: latest submission timestamp (`Last Form Completed` / the Forms
   tables) on or after this month's request date → the current month's form
   specifically is done, even if older ones remain outstanding. A person who
   is 3 behind but submitted this month is CATCHING UP and gets no lateness
   nudge.

Verify both against real records in the fixture session before coding
(including a catching-up case if one exists). Becomes a unit-tested function.

## 2. Tone per rung and sign-off identity — DECIDED 25 Aug 2026

**Sign-off: "Talos Ops"** (from ops@talosnetwork.org). Team identity, never a
personal voice (hard rule 7).

**Vocabulary:** REVISED 25 Aug 2026 — **"progress report"**, per Steve. The
MOU (§C.3/§B.3) says "monthly reflection report"; Steve consciously waived
matching the contract wording ("progress report" is fine legally). The rung-3
obligation sentence still points at the signed agreement, just using the
programme's everyday term.

**The purpose framing** (from the original form request, reusable in gentle
rungs): "This helps us better understand how you are experiencing your
placement, and to respond to any feedback you might share."

**Register anchors** (Steve's own words; middle rungs interpolate):

- Gentlest (week 1 x 1 behind): "Just a quick reminder to complete your
  latest progress report..." — light, assumes good faith, includes the
  purpose framing and the form link.
- Firmest (week 3 x 3+ behind): names the signed obligation. MOU-accurate
  default: "Completing the monthly reflection report is a requirement of your
  Fellowship agreement." Steve's original phrasing was "a condition of your
  funding" — the stipend sits in the separate Scholarship Agreement, so use
  the funding phrasing only if that agreement ties the stipend to programme
  obligations. **TODO: Steve to check the Scholarship Agreement wording.**
  At 3+ depth the supervisor CC is already happening (decision 1), so the
  email is transparent about it ("we've copied in <supervisor>").

Supervisor own-form chases mirror the same registers, professional tone,
anchored on MOU §B.3 at the firm end.

**Additions from the first draft-review session (25 Aug 2026):**
- **The ask is always ONE form**, covering the whole time on placement since
  the last report (or since the start, if none). Never "complete your missed
  forms"; never backfilling. The drafting prompt receives
  `covers_period_since` for this.
- **Every supervisor email offers an out**: if they're not the right person
  to complete these reports, reply and we'll update our records.

**Round 2 (25 Aug 2026):**
- Depth 1 emails keep it simple ("your most recent progress report") — no
  covering-period arithmetic. Depth 2+ names the exact covers-since date
  (last submission date, or the placement start date) — plainly, with no
  meta-talk about backfilling or how the forms work.
- Light never means optional: no "whenever you have a spare moment" energy.
- Supervisor reports are theirs, about the fellow: "your progress report on
  X's placement". Single-fellow supervisor emails are normal prose; the
  line-per-fellow format only for multi-fellow batches. Never name the host
  org back at someone who works there.
- **Grace rule (rules change): a report submitted up to 10 days BEFORE a
  request date counts as covering that request** — someone who submits late
  is not chased days later for a report covering a sliver of placement
  (the Marietta case). 10 mirrors the base's own Expected Reports grace.

## 3 + 5. Nudge memory: a Nudges table in the Placements-MEL base — DECIDED 25 Aug 2026

One table serves as both nudge memory and approval ledger. Alternatives
(state file in the repo, separate base) were considered and rejected — the
state file above all because it would commit fellows' personal data into git
history permanently, hand-roll a race condition between the two workflows
(risking the double-send hard rule), and hide the audit trail from the team.

The Airtable token gains write access to THIS TABLE ONLY; read-only on
everything else in the base.

Fields:

| Field           | Type                                   | Purpose |
|-----------------|----------------------------------------|---------|
| Placement       | Link to Placements                     | Whose chase this is |
| Recipient       | Single select: Fellow / Supervisor     | Who was contacted |
| Rung            | Number (1-3)                           | Week rung when drafted |
| Depth           | Number                                 | Forms behind at drafting time |
| Supervisor CC'd | Checkbox                               | Whether the 3+-depth CC applied |
| Status          | Single select: Pending / Sent / Rejected | The state machine |
| Draft           | Long text                              | Draft as approved; revisions appended above the original |
| Slack thread    | URL/text                               | Permalink to the approval thread |
| Approved by     | Text                                   | Slack user who approved |
| Created at      | Date                                   | When drafted |
| Sent at         | Date                                   | When actually sent |

Status is deliberately three-state: an approved draft is sent seconds later
by the poller, so a separate "Approved" state would never be observed. If a
send fails after approval, the row stays Pending and the bot reports the
failure in the Slack thread. A row with no reply stays Pending forever —
silence is never consent.

## 4. Run cadence and destination — DECIDED 25 Aug 2026

**Draft job: daily at 08:00 Berlin time** (Actions cron 06:00 UTC; drifts to
07:00 local in winter — acceptable for a daily job, noted in runbook).
Daily means every rung fires exactly on its 7/14/21-day mark; most days
produce no drafts and no messages.

**Destination for the trial: DM to Steve** rather than the #form-nudges
channel. The destination is a single config value (a Slack conversation ID);
the documented handover path is switching it to a private channel so a
successor inherits the flow — no code change involved.

## 6. Slack reply allowlist — DECIDED 25 Aug 2026

Steve only (user ID captured during Slack app setup). The poller verifies the
sender's user ID against the allowlist even in the trial DM — it never trusts
the conversation itself — so moving to a channel later adds no new risk.

## 7. Poller cadence — DECIDED 25 Aug 2026

**Every 15 minutes** (Actions cron), plus workflow_dispatch for "act now".
Worst-case lag from approval reply to send: 15 minutes. Chosen over 30 so
that edit-request round-trips ("approve but warmer" → revision → fresh
approval) feel conversational during the trial.

## 8. Pause conditions beyond the checkbox — DECIDED 25 Aug 2026

None. No cohort-wide break dates, no snooze field in v1 (a "skip" reply on
the draft covers known individual situations; `Placement Paused?` covers
longer ones). First-form lateness gets the standard week-1 gentle nudge —
no special first-month grace beyond what the month-anniversary maths already
provides. `Placement Paused?` and completed placements remain unconditional
and are the only automatic silencers.
