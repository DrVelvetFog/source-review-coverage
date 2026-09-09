#!/usr/bin/env python3
"""
ceb scan — find merge commits whose content no review covered.

For every merge commit in a repository, replay the automatic merge of its
parents and compare against what the commit actually contains. The difference
is code that entered the history inside a merge: present in no parent, absent
from the pull-request diff a forge displays, and therefore reviewed by nobody
as a matter of course rather than by accident.

Not every finding is malicious — conflict resolutions land here too, and some
are entirely correct. The point is that none of them were reviewed.

Usage:  python3 scan.py <repo> [--limit N] [--since <rev>]
"""

import argparse
import json
import subprocess
import sys

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from ceb import diff_trees, git, parents_of, replay_merge, tree_of  # noqa: E402


def merge_commits(repo, limit=None, since=None):
    args = ["log", "--merges", "--format=%H"]
    if since:
        args.append(f"{since}..HEAD")
    out, _ = git(*args, repo=repo)
    commits = [c for c in out.splitlines() if c]
    return commits[:limit] if limit else commits


def subject(repo, commit):
    out, _ = git("log", "-1", "--format=%s", commit, repo=repo)
    return out


def classify(diff):
    """Rough triage so a reader can tell noise from signal quickly."""
    added = [l for l in diff.splitlines() if l.startswith("+") and not l.startswith("+++")]
    removed = [l for l in diff.splitlines() if l.startswith("-") and not l.startswith("---")]
    if any("<<<<<<<" in l or ">>>>>>>" in l for l in added + removed):
        return "conflict-marker"
    if added and not removed:
        return "insertion-only"
    return "mixed"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("repo")
    p.add_argument("--limit", type=int)
    p.add_argument("--since")
    p.add_argument("--max-diff-lines", type=int, default=12)
    p.add_argument("--json", action="store_true", help="machine-readable result on stdout")
    a = p.parse_args()

    commits = merge_commits(a.repo, a.limit, a.since)
    say = (lambda *x, **k: None) if a.json else print
    say(f"scanning {len(commits)} merge commits in {a.repo}\n")

    findings = 0
    errors = 0
    result = []
    for c in commits:
        parents = parents_of(c, repo=a.repo)
        if len(parents) < 2:
            continue
        try:
            clean, expected = replay_merge(parents, repo=a.repo)
        except Exception as e:
            errors += 1
            say(f"  ?  {c[:10]}  replay error: {e}")
            continue
        if not expected:
            continue
        actual = tree_of(c, repo=a.repo)
        if actual == expected:
            continue

        findings += 1
        d = diff_trees(expected, actual, repo=a.repo)
        lines = [l for l in d.splitlines()
                 if l.startswith(("+", "-")) and not l.startswith(("+++", "---"))]
        subj = subject(a.repo, c)
        result.append({"commit": c, "subject": subj, "parents": len(parents),
                       "clean_replay": clean, "kind": classify(d),
                       "residual_lines": len(lines)})
        say(f"  ✗  {c[:10]}  {subj[:58]}")
        say(f"     parents={len(parents)} clean_replay={clean} "
            f"kind={classify(d)} residual_lines={len(lines)}")
        for l in lines[:a.max_diff_lines]:
            say(f"       {l[:100]}")
        if len(lines) > a.max_diff_lines:
            say(f"       … {len(lines) - a.max_diff_lines} more")
        say()

    if a.json:
        print(json.dumps({"scan": "merge-commits", "repo": a.repo,
                          "sampled": len(commits), "errors": errors,
                          "identity": len(commits) - errors - findings,
                          "residual": findings,
                          "residual_clean_replay": sum(1 for f in result if f["clean_replay"]),
                          "findings": result}, indent=1))
        return
    print(f"{findings} of {len(commits)} merge commits contain content no parent had.")


if __name__ == "__main__":
    main()
