#!/usr/bin/env python3
"""
Render a verification result as a check-run payload with inline annotations.

  render_check.py verify.json record.json --head-sha SHA [--fail]
                  [--always] [--run-url URL] [--artifact NAME]

Prints the JSON body for POST /repos/{owner}/{repo}/check-runs, or nothing
when there is nothing worth saying: by default a check run is rendered only
when bytes shipped that no approval covers (a residual). --always renders the
verdict for every run, which is what a required check needs.

Each annotation carries the residual hunk itself — the exact bytes are the
point, and they are authoritative where the line numbers are not: positions
are computed on the shipped tree, so on a pull request whose base has moved
the Files-tab placement can drift while the quoted diff cannot.

The conclusion follows fail-on, which the caller has already applied: --fail
means the action is failing this run. Without it, VERIFIED is success and
anything else is neutral — neutral counts as passing for branch protection,
and an honest tool does not paint UNVERIFIED green. Stdlib only.
"""
import argparse
import json
import re
import sys

from render_comment import render

NAME = "source-review-coverage"
MAX_ANNOTATIONS = 50   # the Checks API accepts at most 50 per request


def annotations(residual, level):
    """One annotation per hunk of the residual diff, placed on the shipped
    tree's line numbers (the + side)."""
    anns, path, new_ln = [], None, 0
    first = last = None
    hunk = []

    def flush():
        nonlocal first, last, hunk
        if path and hunk and first is not None:
            anns.append({
                "path": path,
                "start_line": max(first, 1),
                "end_line": max(last or first, 1),
                "annotation_level": level,
                "message": "Shipped with no approval covering it:\n\n"
                           + "\n".join(hunk)[:2000],
            })
        first = last = None
        hunk = []

    for line in residual.splitlines():
        if line.startswith("+++ "):
            flush()
            p = line[4:].split("\t")[0]
            path = None if p == "/dev/null" else p[2:] if p.startswith("b/") else p
        elif line.startswith("@@"):
            flush()
            m = re.match(r"@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@", line)
            new_ln = int(m.group(1)) if m else 1
            hunk = [line]
        elif hunk and line.startswith("+"):
            first, last = (first if first is not None else new_ln), new_ln
            new_ln += 1
            hunk.append(line)
        elif hunk and line.startswith("-"):
            # A deletion holds no line in the shipped file; anchor it where
            # the surrounding context sits.
            first, last = (first if first is not None else new_ln), max(last or new_ln, new_ln)
            hunk.append(line)
        elif hunk and line.startswith(" "):
            new_ln += 1
            hunk.append(line)
        elif line.startswith("diff "):
            flush()
            path = None
    flush()
    return anns


def payload(verify, record, head_sha, fail=False, always=False, run_url=None, artifact=None):
    residual = verify.get("residual") or ""
    if not residual and not always:
        return None
    verdict = verify.get("verdict", "?")
    conclusion = "failure" if fail else ("success" if verdict == "VERIFIED" else "neutral")
    anns = annotations(residual, "failure" if fail else "warning")

    # The comment renderer already says everything the summary should; reuse
    # it and drop the marker line, which only the comment editor needs.
    summary = render(verify, record, run_url=run_url, artifact=artifact, always=True)
    summary = summary.split("\n", 1)[1] if summary.startswith("<!--") else summary
    if len(anns) > MAX_ANNOTATIONS:
        summary += (f"\n{len(anns)} residual hunks; the first {MAX_ANNOTATIONS} are "
                    "annotated inline, the full diff is above.\n")
        anns = anns[:MAX_ANNOTATIONS]

    return {
        "name": NAME,
        "head_sha": head_sha,
        "status": "completed",
        "conclusion": conclusion,
        "output": {
            "title": f"Source review coverage: {verdict}",
            "summary": summary[:60000],
            "annotations": anns,
        },
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("verify")
    ap.add_argument("record")
    ap.add_argument("--head-sha", required=True)
    ap.add_argument("--fail", action="store_true")
    ap.add_argument("--always", action="store_true")
    ap.add_argument("--run-url")
    ap.add_argument("--artifact")
    a = ap.parse_args()
    p = payload(json.load(open(a.verify)), json.load(open(a.record)), a.head_sha,
                fail=a.fail, always=a.always, run_url=a.run_url, artifact=a.artifact)
    if p is not None:
        json.dump(p, sys.stdout, indent=2)
        print()


if __name__ == "__main__":
    main()
