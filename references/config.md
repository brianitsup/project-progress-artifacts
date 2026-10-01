# progress.config.json reference

The config holds everything the sheets need that GitHub doesn't: narrative, the codebase guide, phases, dependency corrections and publish URLs. The template is `assets/progress.config.template.json`. All fields are optional; empty sections are simply not rendered.

## project

| Field | Used on | Notes |
|---|---|---|
| `name` | both | Product name, not the repo slug ("Acme Billing", not "acme-billing-api"). Drives page titles. |
| `client` | report | Who the work is for. For an internal product: "<Your company> (own product)". |
| `owner` | report footer | Person preparing the report. |
| `timezone` | both | IANA zone for dates. Default `Pacific/Guadalcanal`. |
| `summary` | tracker lede, report fallback | One sentence on what the product does. |
| `startDate`, `targetDate` | report | `YYYY-MM-DD`. Only if the user or a doc states it. |

## status

- `overall`: `on_track` | `at_risk` | `off_track` | null. Null derives it from milestone health; the build prints a note when an explicit value disagrees with the derived one.
- `headline`: 1–2 sentences, the first thing a client reads. State where the project is and the one thing that matters most right now. Example: "The MVP is ready for pilot clinics. Two operational-hardening items remain, and neither blocks paid launch."

## milestones

Array; each entry matches a GitHub milestone by `title`, or defines a virtual phase.

```json
{ "title": "Launch readiness", "name": "Security and launch readiness",
  "description": "What the client gets when this is done, in one sentence.",
  "issues": [8, 9, 17, 24], "due": "2026-11-30", "health": null, "clientVisible": true }
```

- `issues` assigns issues that have **no** GitHub milestone to this phase (GitHub milestones always win).
- `due` overrides the GitHub due date; `health` overrides the derived health (use sparingly, e.g. a milestone knowingly paused).
- `clientVisible: false` hides internal milestones (chores, tech debt) from the report while keeping them on the tracker.
- Order in this array sets delivery order for phases without due dates.

## report

- `windowDays`: how far back "recently delivered" looks (default 14). Match the reporting cadence: 7 weekly, 14 fortnightly, 30 monthly.
- `highlights`: outcomes delivered this period, in plain language. The page also lists closed issues from the window automatically, so use highlights for the business meaning ("Clinics can now print end-of-day reports"), not a repeat of issue titles.
- `next`: what happens next period. Leave empty to auto-list in-progress then ready issues.
- `risks`: `{ "risk", "impact": "High|Medium|Low", "mitigation", "owner" }`. Only real, sourced risks. High-impact risks count toward the report's "Needs attention" figure.
- `decisions`: `{ "decision", "owner", "by": "YYYY-MM-DD" }` — things the reader must decide or approve.

### Writing for the report audience

Clients and managers want outcomes, confidence and asks. Use the product's user-facing terms ("printable reports", not "print CSS"). No issue numbers in prose, no internal jargon, no hedging filler. Be direct about slippage: a late milestone stated plainly, with the recovery step, builds more trust than a vague "on track".

## codebase (Dev Tracker "Start here")

Aim for what a competent developer new to the repo needs in their first hour.

- `overview`: 2–3 sentences: architecture shape and the rules that apply everywhere (multi-tenancy, audit, money handling).
- `stack`: short tags.
- `architecture`: 3–6 facts that prevent the classic newcomer mistakes (source of truth for schema, generated files not to edit, how frontend reaches backend, auth model).
- `modules`: `{ "path", "purpose", "issues": [n] }` — top-level areas, with the issues that touch them so a developer picking an issue knows where to look.
- `setup`: `{ "step", "cmd" }` — real commands from the repo's README/docs/scripts, in order, ending with the pre-PR checks.
- `conventions`: rules from AGENTS.md/CONTRIBUTING/lint config that reviewers will enforce.
- `docs`: `{ "title", "path" | "url", "why" }` — what to read next and why.
- `glossary`: `{ "term", "definition" }` — domain terms a newcomer won't know.

## schedule (timeline)

```json
"schedule": { "defaultDays": 7, "dates": { "12": { "start": "2026-10-06", "due": "2026-10-17" } } }
```

- Due and start dates normally come from GitHub, in this order of precedence: `schedule.dates` here, then a line in the issue body, then a GitHub Projects date field whose name contains "due", "target", "deadline" or "end" (or "start").
- The issue-body convention the parser reads, anywhere on its own line (bold markers allowed):
  `Due: 2026-10-17` and optionally `Start: 2026-10-06`. Also accepted: `Due date:`, `Target date:`, `Deadline:`, `Start date:`.
- Use `dates` only for repos where the dates can't live in GitHub yet.
- `defaultDays`: length of the estimated bar for open work with no due date. Estimated bars are hatched and labelled as estimates; they are never presented as commitments.

## dependencyOverrides

```json
{ "add": [ { "blocker": 16, "blocked": 7, "inferred": true, "why": "#7's monitoring criterion is deferred to #16" } ],
  "remove": [ { "blocker": 3, "blocked": 4 } ] }
```

- `inferred: true` draws the edge dashed and labels it "Inferred, not yet recorded in GitHub". Omit it only for an order the user explicitly confirmed.
- `remove` drops a wrong edge parsed from issue text.
- Once the user records a dependency natively in GitHub, delete the override.

## exclude

`labels` and `issues` to leave out entirely (questions, duplicates, discussions filed as issues).

## publish

`devTrackerUrl`, `reportUrl`: the claude.ai artifact URLs, filled after the first publish.

## statusOverrides

```json
"statusOverrides": { "12": { "status": "in_progress", "merged": true, "note": "Merged in PR #66; open for sign-off" } }
```

For facts GitHub can't express: code merged by a PR that doesn't close the issue, an issue being worked without a label or PR. `merged: true` also unblocks the issue's dependants. The note shows in the Dev Tracker register. Remove overrides once GitHub reflects the state (close the issue, add a label, or link the PR with "Closes #n").

## project.titles

`{ "devTracker": "...", "report": "..." }` keeps a page's old name when it is republished at the same link. Use only when the user asks; the default is the standard naming.

## report.taskLabels

`{ "39": "Editor guide for TCSI staff" }` — plain-language names for open work items on the Progress Report timeline, for client audiences where GitHub titles are technical. When `report.highlights` is filled, the "Delivered" list shows only those highlights, not raw closed-issue titles.
