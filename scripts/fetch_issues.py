#!/usr/bin/env python3
"""Fetch everything the progress artifacts need from GitHub into one JSON file.

Usage:
    python3 fetch_issues.py --repo OWNER/REPO [--out docs/progress/data/issues.json]

Auth, in order of preference:
  1. `gh` CLI (uses whatever `gh auth login` set up)
  2. GITHUB_TOKEN / GH_TOKEN env var (fine-grained, Issues+Metadata+Pull requests: read)

Collects: repo metadata, all milestones, all issues (open + closed) with labels,
assignees, milestone, native blocked-by/blocking, parent/sub-issues, closing PRs,
optional Projects v2 "Status" field, and recently merged PRs. Optional fields
that the token can't read are dropped automatically (the query is retried
without them) so a limited token still produces a usable file.
"""
import argparse, json, os, shutil, subprocess, sys, time, urllib.request, urllib.error
from datetime import datetime, timezone

ISSUE_FIELDS_CORE = """
  number title url state stateReason createdAt updatedAt closedAt body
  author { login }
  labels(first: 30) { nodes { name color } }
  assignees(first: 10) { nodes { login } }
  milestone { number title }
  comments { totalCount }
"""
ISSUE_FIELDS_DEPS = """
  blockedBy(first: 50) { nodes { number repository { nameWithOwner } } }
  blocking(first: 50) { nodes { number repository { nameWithOwner } } }
"""
ISSUE_FIELDS_SUB = """
  parent { number }
  subIssues(first: 50) { nodes { number } }
"""
ISSUE_FIELDS_PRS = """
  closedByPullRequestsReferences(first: 10, includeClosedPrs: true) {
    nodes { number title url state merged mergedAt createdAt }
  }
"""
ISSUE_FIELDS_PROJECT = """
  projectItems(first: 5) { nodes {
    project { title }
    fieldValueByName(name: "Status") {
      ... on ProjectV2ItemFieldSingleSelectValue { name }
    }
    fieldValues(first: 20) { nodes {
      ... on ProjectV2ItemFieldDateValue { date field { ... on ProjectV2FieldCommon { name } } }
    } }
  } }
"""
OPTIONAL = [("deps", ISSUE_FIELDS_DEPS), ("sub", ISSUE_FIELDS_SUB),
            ("prs", ISSUE_FIELDS_PRS), ("project", ISSUE_FIELDS_PROJECT)]


def gql(query, variables):
    """Run a GraphQL query via gh, or via token over HTTPS."""
    if shutil.which("gh"):
        args = ["gh", "api", "graphql", "-f", f"query={query}"]
        for k, v in variables.items():
            if v is None:
                continue
            args += ["-F" if isinstance(v, int) else "-f", f"{k}={v}"]
        p = subprocess.run(args, capture_output=True, text=True)
        if p.returncode != 0:
            # gh prints GraphQL errors on stdout as JSON sometimes
            raise RuntimeError(p.stderr.strip() or p.stdout.strip())
        data = json.loads(p.stdout)
    else:
        token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
        if not token:
            sys.exit("No `gh` CLI and no GITHUB_TOKEN/GH_TOKEN set. Install gh and run `gh auth login`, or export a token.")
        req = urllib.request.Request(
            "https://api.github.com/graphql",
            data=json.dumps({"query": query, "variables": variables}).encode(),
            headers={"Authorization": f"bearer {token}", "Content-Type": "application/json"})
        try:
            data = json.loads(urllib.request.urlopen(req, timeout=60).read())
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"HTTP {e.code}: {e.read().decode()[:500]}")
    if data.get("errors"):
        raise RuntimeError(json.dumps(data["errors"])[:800])
    return data["data"]


def fetch_issues(owner, name, optional_keys):
    fields = ISSUE_FIELDS_CORE + "".join(f for k, f in OPTIONAL if k in optional_keys)
    q = f"""query($owner:String!, $name:String!, $cursor:String) {{
      repository(owner:$owner, name:$name) {{
        issues(first: 40, after: $cursor, orderBy: {{field: CREATED_AT, direction: ASC}}) {{
          pageInfo {{ hasNextPage endCursor }}
          nodes {{ {fields} }}
        }}
      }}
    }}"""
    out, cursor = [], None
    while True:
        d = gql(q, {"owner": owner, "name": name, "cursor": cursor})
        page = d["repository"]["issues"]
        out += page["nodes"]
        if not page["pageInfo"]["hasNextPage"]:
            return out
        cursor = page["pageInfo"]["endCursor"]
        time.sleep(0.2)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True, help="OWNER/REPO")
    ap.add_argument("--out", default="docs/progress/data/issues.json")
    a = ap.parse_args()
    owner, name = a.repo.split("/", 1)

    meta_q = """query($owner:String!, $name:String!) {
      repository(owner:$owner, name:$name) {
        nameWithOwner name description url isPrivate
        defaultBranchRef { name }
        primaryLanguage { name }
        languages(first: 8, orderBy:{field:SIZE, direction:DESC}) { nodes { name } }
        milestones(first: 50, orderBy:{field:DUE_DATE, direction:ASC}, states:[OPEN, CLOSED]) {
          nodes { number title description state dueOn closedAt createdAt }
        }
        pullRequests(first: 30, states:[MERGED], orderBy:{field:UPDATED_AT, direction:DESC}) {
          nodes { number title url mergedAt author { login } }
        }
      }
    }"""
    repo = gql(meta_q, {"owner": owner, "name": name})["repository"]

    # Try the richest query first, dropping optional field groups the token/API can't serve.
    keys = [k for k, _ in OPTIONAL]
    dropped = []
    while True:
        try:
            issues = fetch_issues(owner, name, keys)
            break
        except RuntimeError as e:
            if not keys:
                raise
            # Drop the most "optional" remaining group (project first, then prs, sub, deps)
            victim = keys.pop()
            dropped.append(victim)
            print(f"note: dropping optional fields '{victim}' ({str(e)[:160]})", file=sys.stderr)

    payload = {
        "fetchedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "repo": repo,
        "issues": issues,
        "unavailableFields": dropped,
    }
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    with open(a.out, "w") as f:
        json.dump(payload, f, indent=1)
    print(f"wrote {a.out}: {len(issues)} issues, {len(repo['milestones']['nodes'])} milestones"
          + (f"; unavailable: {', '.join(dropped)}" if dropped else ""))


if __name__ == "__main__":
    main()
