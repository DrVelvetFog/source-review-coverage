#!/usr/bin/env bash
# Agent Audit: the coverage and residual sections, generated from a clone.
#
#   audit/run.sh <clone> [--branch main] [--limit 400] [--out audit/out] [--fetch-prs]
#
# Runs the merge-commit scan (content that entered inside a merge commit) and, where
# refs/remotes/pull/* exist, the squash scan (content that entered a squash without
# appearing in the pull request). --fetch-prs runs
#   git fetch origin 'refs/pull/*/head:refs/remotes/pull/*'
# in the clone first; without it nothing touches the network. Writes:
#   <out>/merge.json, <out>/squash.json   the scans' machine-readable results
#   <out>/report.md                       audit/TEMPLATE.md with the generated
#                                         sections filled in
# Stdlib Python and git only. Replay writes unreferenced objects into the clone;
# run it on a copy if the clone must not change.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
tools="$here/../tools"
repo=""; branch=main; limit=400; out="$here/out"; fetch=0
while [ $# -gt 0 ]; do
  case "$1" in
    --branch) branch="$2"; shift 2 ;;
    --limit) limit="$2"; shift 2 ;;
    --out) out="$2"; shift 2 ;;
    --fetch-prs) fetch=1; shift ;;
    -*) echo "unknown option $1" >&2; exit 2 ;;
    *) repo="$1"; shift ;;
  esac
done
[ -n "$repo" ] && [ -d "$repo/.git" ] || { echo "usage: audit/run.sh <clone> [--branch main] [--limit 400] [--out DIR] [--fetch-prs]" >&2; exit 2; }
mkdir -p "$out"
if [ "$fetch" = 1 ]; then
  git -C "$repo" fetch -q origin 'refs/pull/*/head:refs/remotes/pull/*'
fi
python3 "$tools/scan.py" "$repo" --limit "$limit" --json > "$out/merge.json"
if git -C "$repo" show-ref --quiet 'refs/remotes/pull/' 2>/dev/null || [ -n "$(git -C "$repo" for-each-ref 'refs/remotes/pull/' | head -1)" ]; then
  python3 "$tools/scan_squash.py" "$repo" --branch "$branch" --limit "$limit" --json > "$out/squash.json"
else
  echo '{"scan": "squash-commits", "skipped": "no refs/remotes/pull/* in the clone; rerun with --fetch-prs"}' > "$out/squash.json"
fi
python3 - "$here/TEMPLATE.md" "$out" "$repo" "$branch" "$limit" <<'PY'
import json, subprocess, sys
tpl, out, repo, branch, limit = sys.argv[1:6]
m = json.load(open(f"{out}/merge.json"))
q = json.load(open(f"{out}/squash.json"))
head = subprocess.run(["git", "-C", repo, "rev-parse", "--short", branch], capture_output=True, text=True).stdout.strip()
origin = subprocess.run(["git", "-C", repo, "remote", "get-url", "origin"], capture_output=True, text=True).stdout.strip() or repo

cov = ["| scan | sampled | identity or replay | residual | residual with a clean replay |", "|---|---|---|---|---|"]
cov.append(f"| merge commits | {m['sampled']} | {m['identity']} | {m['residual']} | {m['residual_clean_replay']} |")
if "skipped" in q:
    cov.append(f"| squash commits | skipped | | | |")
    squash_note = f"\nSquash scan skipped: {q['skipped']}.\n"
else:
    cov.append(f"| squash commits | {q['checked']} | {q['identity'] + q['replay']} | {q['residual']} | {q['residual_clean_replay']} |")
    squash_note = (f"\nOf {q['checked']} squash commits checked, {q['identity']} shipped the reviewed tree byte for byte and "
                   f"{q['replay']} were the reviewed change replayed onto a moved base, exactly. {q['no_pr']} first-parent "
                   f"commits carried no pull-request number and {q['missing_ref']} had no fetched pull-request ref; those are unverifiable, not clean.\n")
coverage = "\n".join(cov) + squash_note + (
    "\nA residual with a *conflicted* replay is a conflict resolution: someone chose a third form of a hunk at merge "
    "time and no pull request ever showed it. A residual with a *clean* replay is content the merge commit carries "
    "that is in none of its parents and not in the automatic merge either, which no forge displays. Both are unreviewed "
    "by construction; only the second is unusual.\n")

inv = []
for f in sorted(m["findings"], key=lambda f: -f["residual_lines"]):
    inv.append(f"| `{f['commit'][:10]}` | merge, {f['parents']} parents | {'clean' if f['clean_replay'] else 'conflicted'} | {f['residual_lines']} | {f['subject'][:70]} |")
for f in sorted(q.get("findings", []), key=lambda f: -f["residual_lines"]):
    inv.append(f"| `{f['commit'][:10]}` | squash, PR #{f['pr']} | {'clean' if f['clean_replay'] else 'conflicted'} | {f['residual_lines']} | {f['subject'][:70]} |")
inventory = ("| commit | kind | replay | residual lines | subject |\n|---|---|---|---|---|\n" + "\n".join(inv)) if inv else "No residual in the sampled range."

s = open(tpl).read()
s = s.replace("<!-- generated: header -->", f"Repository `{origin}`, branch `{branch}` at `{head}`, most recent {limit} commits of each kind.")
s = s.replace("<!-- generated: coverage -->", coverage)
s = s.replace("<!-- generated: residual -->", inventory)
open(f"{out}/report.md", "w").write(s)
print(f"merge commits: {m['sampled']} sampled, {m['identity']} identity or replay, {m['residual']} residual ({m['residual_clean_replay']} with a clean replay)")
if "skipped" not in q:
    print(f"squash commits: {q['checked']} checked, {q['identity']} identity, {q['replay']} replay, {q['residual']} residual")
print(f"report: {out}/report.md")
PY
