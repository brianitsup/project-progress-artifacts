# project-progress-artifacts

An [Agent Skill](https://agentskills.io) for Claude, Codex CLI, Gemini CLI, Cursor, opencode and other harnesses that read `SKILL.md`.

Generate or refresh a project's two progress artifacts from its GitHub issues — a detailed Dev Tracker (issue flow chart in dependency order, work queue, codebase onboarding guide, issue register) and a high-level Progress Report for clients, managers and supervisors (milestones, % complete, delivered/next, risks) — in one uniform house style, saved to docs/progress/ and published as shareable pages. Use whenever the user asks for a progress report, status update, dev tracker, issue dependency chart/flowchart, roadmap view, milestone tracking, client update, onboarding overview of a repo, or to "update the tracker/report" for any dev project, even if they don't name both artifacts.

## What it produces

Two self-contained HTML sheets per project, in `docs/progress/`, in one shared house style:

- **Dev Tracker**: GitHub issues as a flow chart in dependency order, a work queue (ready, in progress, blocked), a codebase onboarding guide and a full issue register.
- **Progress Report**: milestones, % complete, a timeline (Gantt) with due dates and dependency arrows, recent delivery, what's next, risks and decisions. Written for clients and managers.

## Requirements

- Python 3.9+ (standard library only)
- GitHub CLI (`gh auth login`) or a `GITHUB_TOKEN` with read access to issues

## Due dates

Add a line to each issue body: `Due: 2026-10-17` (optionally `Start: 2026-10-06`). A GitHub Projects date field named "Due"/"Target date"/"Start" also works.

## Quick start (without an agent)

```bash
python3 scripts/fetch_issues.py --repo OWNER/REPO --out docs/progress/data/issues.json
python3 scripts/build.py --progress-dir docs/progress
```

## Install

With the [skills CLI](https://github.com/vercel-labs/skills):

```bash
npx skills add brianitsup/project-progress-artifacts
```

Manually (user scope for Codex, Gemini, Cursor, opencode):

```bash
git clone https://github.com/brianitsup/project-progress-artifacts.git ~/my-skills/project-progress-artifacts
ln -s ../../my-skills/project-progress-artifacts ~/.agents/skills/project-progress-artifacts
```

For Claude, upload the folder as a skill in Settings → Capabilities, or place it in `~/.claude/skills/project-progress-artifacts` for Claude Code.

## License

MIT
