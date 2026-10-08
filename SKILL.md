---
name: project-progress-artifacts
description: "Use for any of Brian's dev projects (a repo with GitHub issues) whenever the user asks for a progress report, status update, client/manager update, dev tracker, issue dependency chart or flowchart, Gantt/timeline, roadmap view, milestone tracking, onboarding overview, or to \"update the tracker/report\", even if they name only one of the two artifacts. Takes precedence over stakeholder-update and roadmap-update for repo-based projects. Generates or refreshes the Dev Tracker and Progress Report from GitHub issues in the house style, in docs/progress/, published as shareable pages."
---

# Project progress artifacts

Two sheets, one house style, generated from GitHub issues:

| Sheet | File | Audience | Job |
|---|---|---|---|
| A · Dev Tracker | `docs/progress/dev-tracker.html` | Developers, new team members | See every issue in dependency order, what can start now, what is blocked, and how the codebase is laid out |
| B · Progress Report | `docs/progress/progress-report.html` | Clients, managers, supervisors | See milestones, % complete, a timeline (Gantt) with due dates and dependency arrows, what was delivered, what's next, risks and decisions |

The pages are rendered by bundled scripts from shared templates (`assets/theme.css`, `assets/common.js`), so every project gets the same look. Never hand-edit the generated HTML: change the config and rebuild, or change the shared assets so every project benefits.

Everything project-specific that isn't in GitHub lives in `docs/progress/progress.config.json` (narrative, codebase guide, phases, dependency overrides, publish URLs). That file is the durable, human-editable part; treat edits already in it as the user's and preserve them.

## Workflow

### 1. Locate the project and anything already in place

- Find the repo root and `owner/repo` (`git remote get-url origin`).
- Check `docs/progress/`. If it exists, this is an **update**: keep `progress.config.json` and `data/history.json`, regenerate everything else.
- Look for legacy progress material this skill should supersede: `ROADMAP.md`, `PROGRESS.md`, `STATUS.md`, `pm/`, `docs/*tracker*`, `docs/*report*`, hand-made HTML dashboards. Don't delete them. Mine them for narrative (milestone names, risks, decisions) and, at the end, tell the user which ones the new sheets replace and offer to replace their content with a link to `docs/progress/`.
- Check for existing published pages: `publish.devTrackerUrl` / `publish.reportUrl` in the config. If empty, list the user's artifacts and look for ones about this project. Earlier pages may carry other names ("Build Order", "Issue Map", "Build Tracker", "Rebuild Progress", "Progress Report"): a detailed issue/dependency page maps to the Dev Tracker, a milestone/status page to the Progress Report. Republishing to an existing URL keeps links the user already shared working; the page takes the standard name (`<Project> Dev Tracker`, `<Project> Progress Report`) so every project reads the same. Confirm the mapping with the user before overwriting, then read each page before publishing to it. Keep an old name (`project.titles`) only if the user asks.
- Read the repo's own agent/workflow files (AGENTS.md, CLAUDE.md, PROJECT_WORKFLOW.md) and follow them.

### 2. Fetch issue data

```bash
python3 <skill-dir>/scripts/fetch_issues.py --repo OWNER/REPO --out docs/progress/data/issues.json
```

It uses `gh` if logged in, else `GITHUB_TOKEN`/`GH_TOKEN`. It pulls all issues (open and closed), milestones, labels, assignees, native blocked-by/blocking, sub-issues, closing PRs, Projects "Status" if readable, and recent merged PRs. Fields the token can't read are dropped and listed in `unavailableFields` rather than failing.

If neither `gh` nor a token is available where you are running (a sandbox, a cloud workspace), don't improvise another route to a private repo: put the script in the repo's scratch area and give the user the one command to run in their own terminal, then continue from the JSON it writes.

### 3. Dry run and read the signals

```bash
python3 <skill-dir>/scripts/build.py --progress-dir docs/progress --check
```

This prints totals, edge counts by source, stages, milestones, the critical path, data-quality warnings, and **cross-references with no dependency recorded**. On a first run it creates `progress.config.json` from the template (unless `--check`).

### 4. Write or refresh the config

Read `references/config.md` for every field and the writing rules. In short:

- **Dependencies.** The script already uses native blocked-by, sub-issues, task-list references, and explicit phrases ("depends on #12", "blocked by #7", "blocks #9"). Review every cross-reference it lists and decide whether it really implies an order; phrases like "tracked in #19" or "follow-up to #7" can point either way, so read the context. Record real ones in `dependencyOverrides.add` with `"inferred": true` and a one-line `why`. Inferred edges draw dashed so nobody mistakes them for recorded facts. If the repo has almost no dependency data, infer from scope (schema before API before UI, decisions before implementation) but keep it modest; a wrong edge is worse than a missing one.
- **Phases.** If GitHub milestones exist, use them (add plain-language `name`/`description` for the client sheet). If there are none, group issues into 2–6 phases via `milestones[].issues` so the client report still has structure.
- **Codebase guide** (Dev Tracker "Start here"). Build it from the repo itself: README/AGENTS.md, package manifests, the directory tree, docs/, CI config. Map each module path to the issues that touch it. Setup commands must be real commands from the repo's docs or scripts, not guesses.
- **Report narrative** (Progress Report). Headline, highlights, next, risks, decisions. Write for a non-developer: outcomes, not issue numbers or implementation detail. Every claim must trace to an issue, PR, doc or something the user said. Never invent dates, owners or budgets; leave them empty and ask.
- **Dates.** The report's timeline reads each issue's `Due: YYYY-MM-DD` (and optional `Start:`) line from its body, or a Projects date field. If the build notes that open issues lack due dates, list them for the user and suggest adding the line; don't invent dates. Use `schedule.dates` only when the user gives you dates that can't go into GitHub yet.
- **Status.** Leave `status.overall` null to derive it from milestone health (late → off track, at risk → at risk). Set it only for a deliberate judgment call, and say why in the headline.

On an update, change only what the new data makes stale; keep the user's wording elsewhere.

### 5. Build

```bash
python3 <skill-dir>/scripts/build.py --progress-dir docs/progress --publish-dir <scratch>/publish
```

Writes the two standalone HTML files (open offline, render GitHub-free), `data/model.json`, and `data/history.json` (one snapshot per day, which feeds the report's trend line). `--publish-dir` gets fragment copies for the Artifact tool.

### 6. Check

Look at both pages once (screenshot or artifact preview) at desktop and phone width. Confirm the headline numbers match the `--check` summary and that no chart text overflows. Fix config, rebuild; don't patch HTML.

### 7. Publish and hand over

- Publish both fragments with the Artifact tool. The `<title>` is fixed by the templates (`<Project> Dev Tracker`, `<Project> Progress Report`); use icon `chart` on first publish. If URLs exist, read each one first and publish to the same URL.
- Save the URLs into `publish.devTrackerUrl` / `publish.reportUrl` so the next run updates the same pages. No rebuild is needed; the URLs aren't rendered.
- Write the files into the repo. Don't commit unless asked; follow the repo's workflow for branches and PRs when committing.
- Tell the user, briefly: overall %, what's ready to start, anything blocked or late, the inferred dependencies to confirm (suggest recording confirmed ones as native GitHub "blocked by" links so the next run doesn't depend on the config), and which legacy files the sheets supersede.

## How status is derived

- **Done**: closed as completed. **Dropped**: closed as not planned or duplicate; excluded from % complete.
- **In progress**: open with an open linked PR, an "in progress"/"review"/"doing" label, or a matching Projects status.
- **Blocked**: open and waiting on at least one unfinished issue, and not already started.
- **Ready**: open with every blocker finished.
- **Stage**: longest-path layer in the dependency graph; stage 1 has no prerequisites. Cycles are broken and reported.
- **Critical path**: the longest chain of unfinished issues.
- **Timeline bars** (finish-to-start): done work spans its first linked PR (or its creation, or its last blocker's close) to its close date. Open work with a due date is planned from the later of today and its blockers' end, up to the due date. Open work without one gets a hatched estimate of `schedule.defaultDays` after its blockers. Arrows link unfinished work to its unfinished prerequisites. A due date on or before a prerequisite's end is a **schedule conflict**: drawn in red, listed as a warning, counted under "Needs attention" with overdue items.
- **Milestone health**: complete; late (past due); at risk (due within 14 days and under 60% done); in progress; not started. A config `health` overrides.

## Uniform formatting

Both sheets share one theme, one component set and one chart renderer, and every project uses the same templates. To change the house style (colors, fonts, a new section), edit `assets/` in the skill, then rebuild each project; don't fork a single project's HTML.
