# Data dictionary — Placements-MEL base (`appPaWOTEPjPt0BVc`)

Verified against the live schema and automation configs on 25 Aug 2026 by
reading the actual formula expressions (not just field names). Items marked
VERIFY remain to be confirmed by hand against real records in the fixture
session.

## The monthly timeline (per placement, month k)

| Day | What happens | Mechanism |
|-----|--------------|-----------|
| Day 0 — k-th month-anniversary of Start Date | Form request email goes out ("the request date") | Airtable automations `Prompt for monthly reporting (Fellows)` / `Prompt for` (Supervisors), triggered when `Months Since Start` increments, via gmailSendEmail |
| Day 7 | Nudge 1 due if current month's form not submitted | this tool |
| Day 10 | `Expected Reports` increments — the base now formally counts the person as behind | formula (10-day grace built in) |
| Day 14 | Nudge 2 due | this tool |
| Day 21 | Nudge 3 due; stop for the month | this tool |

Note the grace-window interaction: between day 7 and day 10, nudge 1 can be
due while `Expected Reports` has not yet incremented. The "is this month's
form done?" predicate therefore uses the DATE route (latest submission vs
request date), never the count route alone. Depth (forms behind) uses the
base's own `Expected Reports − Actual Reports`, which is conservative during
the grace window — acceptable.

## Placements (`tblPat6wJi9lYNOAt`) — fields the tool reads

| Field | What it actually is |
|-------|--------------------|
| `Start Date` / `End Date` | Placement window. Request date = month-anniversaries of Start Date. |
| `Months Since Start` | `DATETIME_DIFF(TODAY(), Start, 'months')` — increments on the plain month-anniversary. The automations watch this. |
| `Expected Reports` | Months since **Start + 10 days**, floored at 0, capped at placement end. The 10-day grace is deliberate. |
| `Actual Reports (Fellows)` | Count of linked `Fellow Reports` (Fellows Forms rows). |
| `Actual Reports (Supervisors)` | Count of linked `Supervisor Reports` (Supervisors Forms rows). |
| `Status (Fellows)` / `(Supervisors)` | actual/expected × 100. **BLANK when Expected = 0.** |
| `Updates? (Fellows)` / `(Supervisors)` | "Up-to-date" if Status ≥ 100, else "Not up-to-date". **TRAP: shows "Not up-to-date" for brand-new placements (Expected = 0, Status blank) even though nothing is due. Never use this as the behind-flag — compute from Expected/Actual and dates.** |
| `Last Form Completed` | **TRAP: despite the generic name, this rolls up the SUPERVISORS Forms `Date`.** |
| `Last Form Completed (Fellows)` | The fellows one — rolls up Fellows Forms `Date Form Completed`. VERIFY the rollup aggregation is MAX (latest) against real records. |
| `Placement Paused?` | Checkbox. Unconditional silencer. |
| `Placement Completed` | `IS_BEFORE(End Date, TODAY())`. Unconditional silencer. |
| `Fellow Email`, `First Name`, `Fellow Form Link`, `Supervisor Form Link`, `Cohort` | Contact/context for drafts. |
| `Supervisor` (link), `Email (from Supervisor)`, `Supervisor First Name` | Supervisor contact via lookups. |

## Sensitive fields — NEVER read into prompts, drafts, or the fixture-derived code paths

Fellows Forms / Supervisors Forms rich text: `What went well?`, `What could
be better?`, `What did you work on?`, `Anything else?`, plus `Satisfaction`
ratings and the `(Recent)` rollups on Placements. The tool reads Forms tables
ONLY for: link-to-Fellow, submission date (`Date Form Completed` / `Date`).

## Supervisors (`tblKk37FAdsFuRwHW`)

Contact info (`Name`, `First Name`, `Email`) plus lookups across their
fellows, including `Days Since Last Form completed by Supervisor`. A
supervisor's own-form chase is per-placement (their reports link to the
fellow's placement), so a supervisor of many fellows can be behind on some
placements and current on others. VERIFY semantics in fixture session.

## Other

- `Reading Group Forms` table: out of scope entirely.
- Automations watch view `viwohsxfw0ZHj4I3s` and have conditional branches —
  VERIFY in fixture session what that view filters (paused? completed?), since
  it defines who actually receives request emails.
- Edge cases answered: before the first report is due, Expected = 0 and
  Status is BLANK → tool does nothing (nothing is due). Expected can never go
  negative (floored at 0) and stops accruing at End Date.
