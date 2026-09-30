#!/usr/bin/env python3
"""Build the two progress artifacts from fetched GitHub data + the project config.

Usage:
    python3 build.py --progress-dir docs/progress [--publish-dir /tmp/publish] [--check]

Reads:
    <progress-dir>/data/issues.json        (from fetch_issues.py)
    <progress-dir>/progress.config.json    (narrative + overrides; created from the template if missing)
    <progress-dir>/data/history.json       (optional; appended to on every build)
Writes:
    <progress-dir>/dev-tracker.html        full standalone HTML (opens offline, committed with the code)
    <progress-dir>/progress-report.html    full standalone HTML
    <progress-dir>/data/model.json         the computed model (handy for diffs and for Claude to read)
    <progress-dir>/data/history.json       one snapshot per day, used for the trend line
    <publish-dir>/dev-tracker.html         fragment version for the Artifact tool (no doctype/html/head/body)
    <publish-dir>/progress-report.html     fragment version for the Artifact tool

--check prints the model summary + data-quality warnings and writes nothing.
"""
import argparse, json, os, re, sys, html
from collections import defaultdict, deque
from datetime import datetime, timezone, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(HERE, "..", "assets")

# ---------- helpers ----------

def load(path, default=None):
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return default


def tzinfo(name):
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo(name)
    except Exception:
        return timezone.utc


def parse_dt(s):
    if not s:
        return None
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


DEP_RE = re.compile(
    r"(?:depends\s+on|dependent\s+on|blocked\s+by|requires|needs|waiting\s+on|prerequisites?:?)\s*:?\s*((?:#\d+[\s,/&and]*)+)",
    re.I)
BLOCKS_RE = re.compile(r"(?:blocks|unblocks|is\s+blocking|required\s+by|prerequisite\s+for)\s*:?\s*((?:#\d+[\s,/&and]*)+)", re.I)
TASK_REF_RE = re.compile(r"^\s*[-*]\s+\[( |x|X)\]\s+(?:[\w.-]+/[\w.-]+)?#(\d+)\b", re.M)
CHECKBOX_RE = re.compile(r"^\s*[-*]\s+\[( |x|X)\]\s+", re.M)
NUM_RE = re.compile(r"#(\d+)")
DATE_LINE_RE = re.compile(
    r"^[\s>*_-]*(?P<k>due(?:\s+date)?|target(?:\s+date)?|deadline|end\s+date|start(?:\s+date)?)[*_\s]*[:：][*_\s]*(?P<d>\d{4}-\d{2}-\d{2})",
    re.I | re.M)
MENTION_RE = re.compile(r"[^\n]{0,70}#(\d+)\b[^\n]{0,40}")


def excerpt(body, limit=260):
    if not body:
        return ""
    text = re.sub(r"```.*?```", " ", body, flags=re.S)
    text = re.sub(r"<!--.*?-->", " ", text, flags=re.S)
    lines = []
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith("#") or s.startswith("|") or s.startswith(">"):
            if lines:
                break
            continue
        if re.match(r"^[-*]\s+\[", s):
            if lines:
                break
            continue
        lines.append(s)
    t = " ".join(lines)
    t = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", t)
    t = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", t)
    t = re.sub(r"[*_`]+", "", t)
    t = re.sub(r"\s+", " ", t).strip()
    return (t[: limit - 1] + "…") if len(t) > limit else t


# ---------- model ----------

IN_PROGRESS_RE = re.compile(r"in[\s_-]?progress|doing|wip|in[\s_-]?review|review|started|active", re.I)


def build_model(raw, cfg, history):
    repo = raw["repo"]
    tz_name = cfg.get("project", {}).get("timezone") or "UTC"
    tz = tzinfo(tz_name)
    fetched = parse_dt(raw["fetchedAt"])
    excl_labels = {l.lower() for l in cfg.get("exclude", {}).get("labels", [])}
    excl_issues = set(cfg.get("exclude", {}).get("issues", []))
    this_repo = repo["nameWithOwner"].lower()
    warnings = []

    issues = {}
    for it in raw["issues"]:
        labels = [l["name"] for l in (it.get("labels") or {}).get("nodes", [])]
        if it["number"] in excl_issues or any(l.lower() in excl_labels for l in labels):
            continue
        body = it.get("body") or ""
        boxes = CHECKBOX_RE.findall(body)
        prs = [
            {"n": p["number"], "title": p["title"], "url": p["url"],
             "state": "merged" if p.get("merged") else p["state"].lower()}
            for p in ((it.get("closedByPullRequestsReferences") or {}).get("nodes") or [])
        ]
        proj_status = None
        for pi in ((it.get("projectItems") or {}).get("nodes") or []):
            v = pi.get("fieldValueByName")
            if v and v.get("name"):
                proj_status = v["name"]
        dates = {}
        for pi in ((it.get("projectItems") or {}).get("nodes") or []):
            for fv in ((pi.get("fieldValues") or {}).get("nodes") or []):
                name = ((fv or {}).get("field") or {}).get("name", "").lower()
                if fv and fv.get("date"):
                    if "start" in name:
                        dates.setdefault("start", fv["date"][:10])
                    elif any(w in name for w in ("due", "target", "deadline", "end")):
                        dates.setdefault("due", fv["date"][:10])
        for m in DATE_LINE_RE.finditer(body):
            dates["start" if m.group("k").lower().startswith("start") else "due"] = m.group("d")
        dates.update({k: v for k, v in (cfg.get("schedule", {}).get("dates", {}).get(str(it["number"])) or {}).items()
                      if k in ("start", "due") and v})
        issues[it["number"]] = {
            "dates": dates,
            "prStarts": [p["createdAt"] for p in ((it.get("closedByPullRequestsReferences") or {}).get("nodes") or []) if p.get("createdAt")],
            "n": it["number"], "title": it["title"].strip(), "url": it["url"],
            "state": it["state"], "stateReason": it.get("stateReason"),
            "createdAt": it["createdAt"], "closedAt": it.get("closedAt"), "updatedAt": it["updatedAt"],
            "labels": labels,
            "assignees": [a["login"] for a in (it.get("assignees") or {}).get("nodes", [])],
            "milestone": (it.get("milestone") or {}).get("title"),
            "prs": prs, "projectStatus": proj_status,
            "criteria": {"done": sum(1 for b in boxes if b.lower() == "x"), "total": len(boxes)},
            "excerpt": excerpt(body), "comments": (it.get("comments") or {}).get("totalCount", 0),
            "_raw": it, "_body": body,
        }

    # Virtual phases: config milestones may list issues. They fill in for missing GitHub
    # milestones, so a repo with no milestones still gets a phased client report.
    for m in cfg.get("milestones", []):
        for n in m.get("issues", []):
            if n in issues and not issues[n]["milestone"]:
                issues[n]["milestone"] = m["title"]
                issues[n]["virtualMilestone"] = True

    # --- edges: (blocker, blocked, kind) ---
    edges = {}

    def add(a, b, kind):
        if a == b or a not in issues or b not in issues:
            return
        key = (a, b)
        rank = {"native": 0, "sub": 1, "text": 2, "config": 3, "inferred": 4}
        if key not in edges or rank[kind] < rank[edges[key]]:
            edges[key] = kind

    external = 0
    mentions = []
    for n, iss in issues.items():
        r = iss["_raw"]
        for b in ((r.get("blockedBy") or {}).get("nodes") or []):
            if b["repository"]["nameWithOwner"].lower() != this_repo:
                external += 1
                continue
            add(b["number"], n, "native")
        for b in ((r.get("blocking") or {}).get("nodes") or []):
            if b["repository"]["nameWithOwner"].lower() == this_repo:
                add(n, b["number"], "native")
        for c in ((r.get("subIssues") or {}).get("nodes") or []):
            add(c["number"], n, "sub")
        if (r.get("parent") or {}).get("number"):
            add(n, r["parent"]["number"], "sub")
        body = iss["_body"]
        for m in DEP_RE.finditer(body):
            for num in NUM_RE.findall(m.group(1)):
                add(int(num), n, "text")
        for m in BLOCKS_RE.finditer(body):
            for num in NUM_RE.findall(m.group(1)):
                add(n, int(num), "text")
        for _, num in TASK_REF_RE.findall(body):
            add(int(num), n, "sub")
        # Every other issue reference is only a hint: phrases like "tracked in #19" or
        # "follow-up to #7" point either way, so Claude reviews them instead of guessing.
        for mm in MENTION_RE.finditer(body):
            ref = int(mm.group(1))
            if ref in issues and ref != n:
                mentions.append({"in": n, "ref": ref, "context": mm.group(0).strip()})
    if external:
        warnings.append(f"{external} blocked-by link(s) point at issues in other repositories; they are not drawn.")

    ov = cfg.get("dependencyOverrides", {})
    for e in ov.get("add", []):
        add(int(e["blocker"]), int(e["blocked"]), "inferred" if e.get("inferred") else "config")
    for e in ov.get("remove", []):
        edges.pop((int(e["blocker"]), int(e["blocked"])), None)

    # --- cycle breaking (DFS back edges) ---
    adj = defaultdict(list)
    for (a, b) in edges:
        adj[a].append(b)
    color, back = {}, []

    def dfs(u):
        color[u] = 1
        for v in sorted(adj[u]):
            if color.get(v) == 1:
                back.append((u, v))
            elif not color.get(v):
                dfs(v)
        color[u] = 2
    sys.setrecursionlimit(10000)
    for n in sorted(issues):
        if not color.get(n):
            dfs(n)
    for e in back:
        warnings.append(f"Dependency cycle: #{e[0]} → #{e[1]} closes a loop; that link is ignored for ordering.")
        edges.pop(e, None)

    blocked_by, blocks = defaultdict(list), defaultdict(list)
    for (a, b), k in edges.items():
        blocked_by[b].append(a)
        blocks[a].append(b)

    # --- status ---
    def status_of(iss):
        if iss["state"] == "CLOSED":
            return "dropped" if iss["stateReason"] in ("NOT_PLANNED", "DUPLICATE") else "done"
        return None

    for n, iss in issues.items():
        iss["status"] = status_of(iss)
    for n, iss in issues.items():
        if iss["status"]:
            continue
        open_blockers = [b for b in blocked_by[n] if issues[b]["status"] not in ("done", "dropped")]
        signals = [iss["projectStatus"] or ""] + iss["labels"]
        has_open_pr = any(p["state"] == "open" for p in iss["prs"])
        started = has_open_pr or any(IN_PROGRESS_RE.search(s) for s in signals if s)
        if open_blockers and not started:
            iss["status"] = "blocked"
        elif started:
            iss["status"] = "in_progress"
        else:
            iss["status"] = "ready"
        iss["openBlockers"] = open_blockers

    # --- stages (longest-path layering in dependency order) ---
    indeg = {n: len(blocked_by[n]) for n in issues}
    q = deque(sorted(n for n in issues if indeg[n] == 0))
    stage = {n: 0 for n in issues}
    order = []
    while q:
        u = q.popleft()
        order.append(u)
        for v in sorted(blocks[u]):
            stage[v] = max(stage[v], stage[u] + 1)
            indeg[v] -= 1
            if indeg[v] == 0:
                q.append(v)

    # --- critical path over open work (longest chain of not-done issues) ---
    open_set = {n for n, i in issues.items() if i["status"] not in ("done", "dropped")}
    best, prev = {}, {}
    for u in order:
        if u not in open_set:
            continue
        cand = [(best[p], p) for p in blocked_by[u] if p in open_set and p in best]
        if cand:
            l, p = max(cand)
            best[u], prev[u] = l + 1, p
        else:
            best[u] = 1
    crit = []
    if best:
        end = max(best, key=lambda k: (best[k], -k))
        while end is not None:
            crit.append(end)
            end = prev.get(end)
        crit.reverse()
    if len(crit) < 2:
        crit = []

    # --- milestones ---
    ms_meta = {m["title"]: m for m in repo["milestones"]["nodes"]}
    ms_cfg = {m["title"]: m for m in cfg.get("milestones", [])}
    groups = defaultdict(list)
    for n, iss in issues.items():
        groups[iss["milestone"] or "—"].append(n)
    today = fetched.astimezone(tz).date()
    milestones = []
    virtual_titles = [m["title"] for m in cfg.get("milestones", []) if m["title"] not in ms_meta]
    ordered_titles = list(ms_meta) + [t for t in virtual_titles if t in groups] + \
        [t for t in groups if t not in ms_meta and t not in virtual_titles]
    for title in ordered_titles:
        ns = groups.get(title, [])
        m = ms_meta.get(title, {})
        c = ms_cfg.get(title, {})
        if not ns and m.get("state") == "CLOSED":
            continue
        counted = [n for n in ns if issues[n]["status"] != "dropped"]
        done = sum(1 for n in counted if issues[n]["status"] == "done")
        total = len(counted)
        due = c.get("due") or (m.get("dueOn") or "")[:10] or None
        pct = round(100 * done / total) if total else 0
        if total and done == total:
            health = "complete"
        elif due and datetime.fromisoformat(due).date() < today:
            health = "late"
        elif due and total and (datetime.fromisoformat(due).date() - today).days <= 14 and pct < 60:
            health = "at_risk"
        elif any(issues[n]["status"] in ("in_progress",) for n in counted) or done:
            health = "active"
        else:
            health = "not_started"
        if c.get("health"):
            health = c["health"]
        milestones.append({
            "title": title if title != "—" else "No milestone",
            "key": title,
            "name": c.get("name") or (title if title != "—" else "Unscheduled work"),
            "description": c.get("description") or (m.get("description") or "").strip(),
            "due": due, "state": m.get("state", "OPEN"), "total": total, "done": done, "pct": pct,
            "inProgress": sum(1 for n in counted if issues[n]["status"] == "in_progress"),
            "blocked": sum(1 for n in counted if issues[n]["status"] == "blocked"),
            "health": health, "clientVisible": c.get("clientVisible", title != "—"),
            "minStage": min((stage[n] for n in ns), default=0),
            "order": len(milestones),
        })
    # dependency order: milestones sorted by due date, then by earliest stage
    milestones.sort(key=lambda m: (m["key"] == "—", m["due"] or "9999", m["order"]))
    ms_index = {m["key"]: i for i, m in enumerate(milestones)}
    ms_edges = set()
    for (a, b) in edges:
        ma, mb = issues[a]["milestone"] or "—", issues[b]["milestone"] or "—"
        if ma != mb and ma in ms_index and mb in ms_index:
            ms_edges.add((ma, mb))

    # --- stats ---
    counted = [i for i in issues.values() if i["status"] != "dropped"]
    stats = {k: sum(1 for i in counted if i["status"] == k) for k in ("done", "in_progress", "ready", "blocked")}
    stats["total"] = len(counted)
    stats["dropped"] = len(issues) - len(counted)
    stats["pct"] = round(100 * stats["done"] / stats["total"]) if stats["total"] else 0
    since = fetched - timedelta(days=int(cfg.get("report", {}).get("windowDays", 14)))
    recent_done = sorted(
        [i for i in counted if i["status"] == "done" and i["closedAt"] and parse_dt(i["closedAt"]) >= since],
        key=lambda i: i["closedAt"], reverse=True)
    stats["closedInWindow"] = len(recent_done)
    stats["windowDays"] = int(cfg.get("report", {}).get("windowDays", 14))

    # --- schedule (for the timeline): finish-to-start over the dependency graph ---
    sched_cfg = cfg.get("schedule", {})
    default_days = int(sched_cfg.get("defaultDays", 7))
    D = lambda s_: datetime.fromisoformat(s_[:10]).date()
    local = lambda iso: parse_dt(iso).astimezone(tz).date()
    sched = {}
    for n in order:
        i = issues[n]
        dt = i["dates"]
        bl = [sched[b] for b in blocked_by[n] if b in sched]
        blocker_end = max((b["end"] for b in bl), default=None)
        due = D(dt["due"]) if dt.get("due") else None
        start = D(dt["start"]) if dt.get("start") else None
        pr_start = min((local(x) for x in i["prStarts"]), default=None)
        if i["status"] in ("done", "dropped"):
            end = local(i["closedAt"]) if i["closedAt"] else today
            if not start or start > end:
                start = pr_start or max([local(i["createdAt"])] + ([blocker_end] if blocker_end else []))
                if start > end:
                    start = local(i["createdAt"])
            kind = "actual"
        else:
            earliest = today if not blocker_end else max(today, blocker_end + timedelta(days=1))
            if not start:
                start = min(pr_start or today, today) if i["status"] == "in_progress" else earliest
            if due:
                end, kind = max(due, start), "planned"
                if start > due:
                    start = due
            else:
                end, kind = start + timedelta(days=default_days - 1), "estimated"
        conflicts = [b for b in blocked_by[n] if b in sched and due and sched[b]["end"] >= due
                     and issues[n]["status"] not in ("done", "dropped")]
        sched[n] = {"start": start, "end": end, "kind": kind, "due": due,
                    "overdue": bool(due and due < today and i["status"] not in ("done", "dropped")),
                    "conflicts": conflicts}
    for m in milestones:
        ns = [n for n in groups.get(m["key"], []) if n in sched and issues[n]["status"] != "dropped"]
        m["start"] = min((sched[n]["start"] for n in ns), default=None)
        m["end"] = max((sched[n]["end"] for n in ns), default=None)
        m["start"] = m["start"].isoformat() if m["start"] else None
        m["end"] = m["end"].isoformat() if m["end"] else None
    open_dated = sum(1 for n in open_set if sched[n]["due"])
    stats["overdue"] = sum(1 for n in open_set if sched[n]["overdue"])
    stats["conflicts"] = sum(1 for n in open_set if sched[n]["conflicts"])
    stats["openDated"], stats["open"] = open_dated, len(open_set)
    for n in sorted(open_set):
        if sched[n]["conflicts"]:
            warnings.append(f"#{n} is due {sched[n]['due']} but its blocker(s) " + ", ".join(
                f"#{b} (ends {sched[b]['end']})" for b in sched[n]["conflicts"]) + " finish on or after that date.")

    # --- data quality ---
    no_ms = [n for n in open_set if not issues[n]["milestone"]]
    if no_ms and len(milestones) > 1:
        warnings.append(f"{len(no_ms)} open issue(s) have no milestone: " + ", ".join(f"#{n}" for n in sorted(no_ms)[:12]))
    isolated = [n for n in open_set if not blocked_by[n] and not blocks[n]]
    if len(open_set) >= 4 and len(isolated) / max(1, len(open_set)) > 0.5:
        warnings.append(f"{len(isolated)} of {len(open_set)} open issues have no recorded dependencies; ordering for them falls back to milestone and issue number.")
    miss = raw.get("unavailableFields") or []
    if any(k in miss for k in ("deps", "sub")):
        warnings.append("Native GitHub dependencies or sub-issues could not be read; only text and config dependencies are shown.")
    notes = []
    if "project" in miss:
        notes.append("Projects board Status was not readable (run `gh auth refresh -s read:project` to use it for in-progress detection).")
    if open_set and open_dated < len(open_set):
        notes.append(f"{len(open_set) - open_dated} of {len(open_set)} open issues have no due date; the timeline "
                     f"estimates them at {default_days} days after their blockers. Add a 'Due: YYYY-MM-DD' line to the issue body.")
    drawn = set(edges)
    mentions = [m for m in mentions if (m["ref"], m["in"]) not in drawn and (m["in"], m["ref"]) not in drawn]

    # --- history snapshot (one per local day) ---
    day = fetched.astimezone(tz).date().isoformat()
    snap = {"date": day, "total": stats["total"], "done": stats["done"], "inProgress": stats["in_progress"],
            "blocked": stats["blocked"], "pct": stats["pct"]}
    history = [h for h in (history or []) if h["date"] != day] + [snap]
    history.sort(key=lambda h: h["date"])

    out_issues = []
    for n in sorted(issues, key=lambda n: (stage[n], ms_index.get(issues[n]["milestone"] or "—", 99), n)):
        i = issues[n]
        out_issues.append({
            "n": n, "title": i["title"], "url": i["url"], "status": i["status"], "stage": stage[n],
            "milestone": i["milestone"], "labels": i["labels"], "assignees": i["assignees"],
            "blockedBy": sorted(blocked_by[n]), "blocks": sorted(blocks[n]),
            "openBlockers": sorted(i.get("openBlockers", [])), "prs": i["prs"], "criteria": i["criteria"],
            "excerpt": i["excerpt"], "createdAt": i["createdAt"], "closedAt": i["closedAt"],
            "projectStatus": i["projectStatus"], "critical": n in crit,
            "unblocksCount": len(descendants(n, blocks)),
            "schedule": {k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in sched[n].items()},
        })

    p = dict(cfg.get("project", {}))
    p.setdefault("name", repo["name"])
    p["repo"] = repo["nameWithOwner"]
    p["repoUrl"] = repo["url"]
    p["repoDescription"] = repo.get("description") or ""
    p["timezone"] = tz_name
    return {
        "schema": 1,
        "generatedAt": fetched.isoformat(),
        "asOf": fetched.astimezone(tz).strftime("%-d %b %Y, %H:%M") + f" ({tz_name})",
        "asOfDate": day,
        "today": today.isoformat(),
        "project": p,
        "status": derive_status(cfg.get("status", {}), milestones),
        "codebase": cfg.get("codebase", {}),
        "report": cfg.get("report", {}),
        "stats": stats,
        "milestones": milestones,
        "milestoneEdges": [{"from": a, "to": b} for a, b in sorted(ms_edges)],
        "issues": out_issues,
        "edges": [{"from": a, "to": b, "kind": k} for (a, b), k in sorted(edges.items())],
        "criticalPath": crit,
        "recentDone": [{"n": i["n"], "title": i["title"], "url": i["url"], "closedAt": i["closedAt"],
                        "milestone": i["milestone"]} for i in recent_done],
        "recentPRs": [{"n": x["number"], "title": x["title"], "url": x["url"], "mergedAt": x["mergedAt"]}
                      for x in repo.get("pullRequests", {}).get("nodes", [])[:15]],
        "warnings": warnings,
        "notes": notes,
        "mentionsToReview": mentions,
        "history": history,
    }, history


def derive_status(status, milestones):
    """Overall health: the config value wins; otherwise derive it from milestone health."""
    st = dict(status or {})
    healths = {m["health"] for m in milestones if m["clientVisible"]}
    derived = "off_track" if "late" in healths else "at_risk" if "at_risk" in healths else "on_track"
    st["derived"] = derived
    if not st.get("overall"):
        st["overall"] = derived
    return st


def descendants(n, blocks):
    seen, st = set(), list(blocks.get(n, []))
    while st:
        u = st.pop()
        if u in seen:
            continue
        seen.add(u)
        st.extend(blocks.get(u, []))
    return seen


# ---------- render ----------

def render(template_name, model, fragment):
    with open(os.path.join(ASSETS, "theme.css")) as f:
        css = f.read()
    with open(os.path.join(ASSETS, "common.js")) as f:
        common = f.read()
    with open(os.path.join(ASSETS, template_name)) as f:
        tpl = f.read()
    title = {
        "dev-tracker.template.html": f"{model['project']['name']} Dev Tracker",
        "progress-report.template.html": f"{model['project']['name']} Progress Report",
    }[template_name]
    data = json.dumps(model, ensure_ascii=False).replace("</", "<\\/")
    body = (tpl.replace("/*__THEME_CSS__*/", css)
               .replace("/*__COMMON_JS__*/", common)
               .replace("__TITLE__", html.escape(title))
               .replace("\"__MODEL_JSON__\"", data))
    if fragment:
        return body
    return ("<!doctype html>\n<html lang=\"en\">\n<head>\n<meta charset=\"utf-8\">\n"
            "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1, viewport-fit=cover\">\n"
            "<meta name=\"generator\" content=\"project-progress-artifacts\">\n</head>\n<body>\n"
            + body + "\n</body>\n</html>\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--progress-dir", default="docs/progress")
    ap.add_argument("--publish-dir")
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    d = a.progress_dir
    raw = load(os.path.join(d, "data", "issues.json"))
    if not raw:
        sys.exit(f"missing {d}/data/issues.json — run fetch_issues.py first")
    cfg_path = os.path.join(d, "progress.config.json")
    cfg = load(cfg_path)
    if cfg is None:
        cfg = load(os.path.join(ASSETS, "progress.config.template.json"))
        cfg["project"]["name"] = raw["repo"]["name"]
        if not a.check:
            with open(cfg_path, "w") as f:
                json.dump(cfg, f, indent=2)
            print(f"created {cfg_path} from template — fill in the narrative fields and rebuild")
    history = load(os.path.join(d, "data", "history.json"), [])
    model, history = build_model(raw, cfg, history)

    s = model["stats"]
    print(f"{model['project']['name']}: {s['total']} issues | {s['pct']}% done | "
          f"done {s['done']} · in progress {s['in_progress']} · ready {s['ready']} · blocked {s['blocked']} · dropped {s['dropped']}")
    print(f"edges: {len(model['edges'])} ({', '.join(f'{k}={v}' for k, v in sorted(count_kinds(model['edges']).items()))}); "
          f"stages: {1 + max((i['stage'] for i in model['issues']), default=0)}; milestones: {len(model['milestones'])}; "
          f"critical path: {' → '.join('#'+str(n) for n in model['criticalPath']) or 'none'}")
    for w in model["warnings"]:
        print("warning:", w)
    for w in model["notes"]:
        print("note:", w)
    st = model["status"]
    if st.get("overall") != st.get("derived"):
        print(f"note: config sets overall status '{st.get('overall')}' but milestone health suggests "
              f"'{st.get('derived')}' — confirm the override is still deliberate.")
    if model["mentionsToReview"]:
        print("cross-references with no dependency recorded (decide whether each implies an order; "
              "record real ones in dependencyOverrides):")
        for m in model["mentionsToReview"]:
            print(f"  #{m['in']} mentions #{m['ref']}: {m['context']}")
    if a.check:
        return

    os.makedirs(os.path.join(d, "data"), exist_ok=True)
    with open(os.path.join(d, "data", "model.json"), "w") as f:
        json.dump(model, f, indent=1, ensure_ascii=False)
    with open(os.path.join(d, "data", "history.json"), "w") as f:
        json.dump(history, f, indent=1)
    for tpl, name in (("dev-tracker.template.html", "dev-tracker.html"),
                      ("progress-report.template.html", "progress-report.html")):
        with open(os.path.join(d, name), "w") as f:
            f.write(render(tpl, model, fragment=False))
        if a.publish_dir:
            os.makedirs(a.publish_dir, exist_ok=True)
            with open(os.path.join(a.publish_dir, name), "w") as f:
                f.write(render(tpl, model, fragment=True))
    print(f"wrote {d}/dev-tracker.html, {d}/progress-report.html" + (f" (+ publish copies in {a.publish_dir})" if a.publish_dir else ""))


def count_kinds(edges):
    c = defaultdict(int)
    for e in edges:
        c[e["kind"]] += 1
    return c


if __name__ == "__main__":
    main()
