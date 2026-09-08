#!/usr/bin/env python3
"""
Render a verification result as a pull-request comment.

  render_comment.py verify.json record.json [--run-url URL] [--artifact NAME]
                    [--always] [--max-diff N]

Prints the Markdown body, or nothing when there is nothing worth saying: by
default a comment is rendered only when bytes shipped that no approval covers
(a residual). --always renders the verdict table for every run.

The body carries a hidden marker so the poster can find and edit its earlier
comment instead of adding another. The residual is rendered as a diff, never
as a bare pass/fail: the exact bytes are the point. Stdlib only.
"""
import argparse
import json
import sys

MARKER = "<!-- source-review-coverage -->"
SIX = ("A pass establishes review coverage and nothing else: not correctness, not that a human "
       "read anything, not truthful authorship, not reviewer independence, not existence at a "
       "time, not compliance.")


def short(h):
    h = (h or "").split(":", 1)[-1]
    return h[:12] if h else "?"


def render(verify, record, run_url=None, artifact=None, always=False, max_diff=12000):
    steps = verify.get("steps", [])
    residual = verify.get("residual") or ""
    if not residual and not always:
        return ""

    verdict = verify.get("verdict", "?")
    by = {s["step"]: s for s in steps}
    out = [MARKER, f"### Source review coverage: `{verdict}`", ""]

    mt = by.get("merge transform")
    if mt:
        out.append(f"- **merge transform** — {mt['status']}: {mt['detail']}")
    ab = [s for s in steps if s["step"] in ("approval binding", "approval")]
    for s in ab:
        out.append(f"- **{s['step']}** — {s['status']}: {s['detail']}")
    sig = by.get("signatures")
    if sig:
        out.append(f"- **signatures** — {sig['status']}: {sig['detail']}")
    out.append("")

    approvals = record.get("approvals") or []
    if approvals:
        out += ["| approver | approved revision | tree | when | source |", "|---|---|---|---|---|"]
        for a in approvals:
            out.append(f"| {a.get('approver') or '?'} | `{short(a.get('commit'))}` | "
                       f"`{short(a.get('over_tree_hash'))}` | {a.get('submitted_at') or '—'} | "
                       f"{a.get('source') or '—'} |")
        out.append("")
    else:
        out.append("No approvals are bound to this revision.")
        out.append("")

    if residual:
        out.append("**Residual — bytes that shipped with no approval covering them.** These were "
                   "produced at merge time (a hand-resolved conflict, an edit inside the merge "
                   "commit, or a push after the last approval), so no review covered them by "
                   "construction. Review these lines specifically.")
        out.append("")
        body = residual
        note = ""
        if len(body) > max_diff:
            body, note = body[:max_diff], f"\n… truncated at {max_diff} characters; the full diff is in the artifact."
        out += ["```diff", body.rstrip("\n"), "```" + note, ""]

    shipped = short((record.get("change") or {}).get("tree_hash"))
    tail = f"Shipped tree `{shipped}`."
    if run_url:
        tail += f" Record, statement and signature: [workflow run]({run_url})"
        tail += f" (artifact `{artifact}`)." if artifact else "."
    out += [tail, "", f"<sub>{SIX}</sub>", ""]
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("verify")
    ap.add_argument("record")
    ap.add_argument("--run-url")
    ap.add_argument("--artifact")
    ap.add_argument("--always", action="store_true")
    ap.add_argument("--max-diff", type=int, default=12000)
    a = ap.parse_args()
    sys.stdout.write(render(json.load(open(a.verify)), json.load(open(a.record)),
                            run_url=a.run_url, artifact=a.artifact, always=a.always,
                            max_diff=a.max_diff))


if __name__ == "__main__":
    main()
