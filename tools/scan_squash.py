#!/usr/bin/env python3
"""
Squash-residual scan for forge-hosted repositories.

Most repositories squash-merge, which discards the reviewed head from the main
history. GitHub keeps it at refs/pull/<n>/head, and the default squash message
carries the PR number — so the reviewed state is recoverable:

    fetch  refs/pull/*/head
    for each first-parent commit "… (#N)":
        base     := commit^        (what it landed on)
        reviewed := pull/N         (what a reviewer saw)
        expected := merge-tree(base, reviewed)
        residual := diff(expected, commit^{tree})

A residual is content that entered the default branch without appearing in the
pull request. Conflict resolution is the usual cause; it is unreviewed either
way, because no diff a reviewer opened ever contained it.

Usage:  python3 scan_squash.py <repo> [--branch main] [--limit 200]
"""

import argparse
import json
import re
import sys

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from ceb import diff_trees, git, merge_tree, tree_of  # noqa: E402

PR = re.compile(r"\(#(\d+)\)\s*$")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("repo")
    p.add_argument("--branch", default="main")
    p.add_argument("--limit", type=int, default=200)
    p.add_argument("--show", type=int, default=10)
    p.add_argument("--json", action="store_true", help="machine-readable result on stdout")
    a = p.parse_args()

    out, _ = git("log", "--first-parent", "--format=%H%x00%s",
                 f"-{a.limit}", a.branch, repo=a.repo)

    checked = identity = replayed = 0
    missing_ref = no_pr = 0
    findings = []

    for line in out.splitlines():
        sha, _, subj = line.partition("\0")
        m = PR.search(subj)
        if not m:
            no_pr += 1
            continue
        n = m.group(1)
        head = f"refs/remotes/pull/{n}"
        _, rc = git("rev-parse", "--verify", head, repo=a.repo, check=False)
        if rc != 0:
            missing_ref += 1
            continue

        base, rc = git("rev-parse", f"{sha}^", repo=a.repo, check=False)
        if rc != 0:
            continue

        shipped = tree_of(sha, repo=a.repo)
        reviewed = tree_of(head, repo=a.repo)
        checked += 1

        if shipped == reviewed:
            identity += 1
            continue

        clean, expected = merge_tree(base, head, repo=a.repo)
        if expected == shipped:
            replayed += 1
            continue

        d = diff_trees(expected, shipped, repo=a.repo) if expected else ""
        lines = [l for l in d.splitlines()
                 if l.startswith(("+", "-")) and not l.startswith(("+++", "---"))]
        findings.append((sha, n, subj, clean, len(lines), lines))

    if a.json:
        print(json.dumps({"scan": "squash-commits", "repo": a.repo, "branch": a.branch,
                          "checked": checked, "no_pr": no_pr, "missing_ref": missing_ref,
                          "identity": identity, "replay": replayed,
                          "residual": len(findings),
                          "residual_clean_replay": sum(1 for f in findings if f[3]),
                          "findings": [{"commit": f[0], "pr": int(f[1]), "subject": f[2],
                                        "clean_replay": f[3], "residual_lines": f[4]}
                                       for f in findings]}, indent=1))
        return
    print(f"repo            : {a.repo}")
    print(f"squash commits  : {checked} checked "
          f"({no_pr} without a PR number, {missing_ref} with no fetched PR ref)")
    print(f"  identity      : {identity}   (shipped tree IS the reviewed tree)")
    print(f"  replay        : {replayed}   (base moved; shipped == base + reviewed change)")
    print(f"  RESIDUAL      : {len(findings)}   (content no reviewer saw)")
    print()

    for sha, n, subj, clean, count, lines in sorted(findings, key=lambda f: f[4])[:a.show]:
        flag = "CLEAN REPLAY" if clean else "conflicted"
        print(f"  ✗ {sha[:10]} PR #{n:<6} {flag:<13} residual_lines={count}")
        print(f"    {subj[:88]}")
        for l in lines[:6]:
            print(f"      {l[:96]}")
        print()


if __name__ == "__main__":
    main()
