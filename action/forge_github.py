#!/usr/bin/env python3
"""
Read review state from GitHub, and nothing else.

  forge_github.py pr-for-commit OWNER/REPO SHA   -> the number of the merged PR
                                                    whose merge commit is SHA, or ""
  forge_github.py approvals OWNER/REPO NUMBER    -> JSON: the PR's coordinates and
                                                    its effective approvals

An "effective approval" is a user's most recent review on the PR when that
review's state is APPROVED. A later CHANGES_REQUESTED or a dismissal by the
same user supersedes an earlier approval, which is how the forge treats it too.
Each approval names the commit it was given on and that commit's tree, read
from the git data API so a revision that was later force-pushed away can still
be bound (rule R3). Nothing here is trusted by the verifier: the record carries
these as the forge's assertions, and coverage is recomputed from the trees.

Token: GITHUB_TOKEN or GH_TOKEN from the environment — the workflow's own token
is enough (pull-requests: read). Never a personal token. Stdlib only.
"""
import json
import os
import sys
import urllib.error
import urllib.request

API = os.environ.get("GITHUB_API_URL", "https://api.github.com")


def token():
    t = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if not t:
        sys.exit("forge_github: GITHUB_TOKEN is not set")
    return t


def get(path, params=None):
    url = f"{API}{path}"
    if params:
        url += "?" + "&".join(f"{k}={v}" for k, v in params.items())
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {token()}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "source-review-coverage",
    })
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        sys.exit(f"forge_github: GET {path} -> {e.code} {e.reason}")


def paginate(path):
    page, out = 1, []
    while True:
        batch = get(path, {"per_page": 100, "page": page})
        out.extend(batch)
        if len(batch) < 100:
            return out
        page += 1


def pr_for_commit(repo, sha):
    for pr in get(f"/repos/{repo}/commits/{sha}/pulls"):
        if pr.get("merged_at") and pr.get("merge_commit_sha") == sha:
            return pr["number"]
    return None


def approvals(repo, number):
    pr = get(f"/repos/{repo}/pulls/{number}")
    reviews = paginate(f"/repos/{repo}/pulls/{number}/reviews")
    reviews.sort(key=lambda r: (r.get("submitted_at") or "", r.get("id", 0)))
    latest = {}
    for r in reviews:
        user = (r.get("user") or {}).get("login")
        if user and r.get("state") not in ("COMMENTED", "PENDING"):
            latest[user] = r
    out = []
    for user, r in latest.items():
        if r.get("state") != "APPROVED":
            continue
        commit = r.get("commit_id")
        tree = get(f"/repos/{repo}/git/commits/{commit}").get("tree", {}).get("sha") if commit else None
        out.append({
            "approver": user,
            "commit": commit,
            "tree": tree,
            "review_id": r.get("id"),
            "submitted_at": r.get("submitted_at"),
            "state": "APPROVED",
            "source": "forge-api",
        })
    out.sort(key=lambda a: (a["submitted_at"] or "", a["review_id"] or 0))
    return {
        "pr": {
            "number": pr["number"],
            "head_sha": pr["head"]["sha"],
            "base_sha": pr["base"]["sha"],
            "base_ref": pr["base"]["ref"],
            "head_repo": (pr["head"].get("repo") or {}).get("full_name"),
            "merged": bool(pr.get("merged_at")),
            "merge_commit_sha": pr.get("merge_commit_sha"),
        },
        "approvals": out,
    }


def main(argv):
    if len(argv) == 4 and argv[1] == "pr-for-commit":
        n = pr_for_commit(argv[2], argv[3])
        print(n if n is not None else "")
    elif len(argv) == 4 and argv[1] == "approvals":
        json.dump(approvals(argv[2], int(argv[3])), sys.stdout, indent=2)
        print()
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main(sys.argv)
