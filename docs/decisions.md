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

### Depth (total forms behind expectation)

`Expected Reports` minus `Actual Reports` from the Placements formulas. Depth
never decides WHETHER to nudge — only how the nudge reads, and whether the
supervisor is copied:

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

**Vocabulary:** the programme's own term is **"monthly reflection report"**
(MOU §C.3 fellows / §B.3 host organisations) — use it, not "progress form".

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

## 3. Nudges table shape — pending

## 4. Run cadence and summary destination — pending

## 5. Nudges table ledger fields — pending

## 6. Slack reply allowlist — pending (start: Steve only)

## 7. Poller cadence and Slack channel — pending

## 8. Pause conditions beyond the checkbox — pending
