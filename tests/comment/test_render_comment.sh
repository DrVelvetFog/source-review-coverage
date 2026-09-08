#!/usr/bin/env bash
# The pull-request comment: rendered only for a residual (or always), carries
# the exact residual hunk as a diff, the approvals table, and the §6 line, and
# is truncated at a fixed size. Offline. Run: bash tests/comment/test_render_comment.sh
set -uo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CEB="$here/../../tools/ceb.py"; RENDER="$here/../../tools/render_comment.py"
T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
pass=0; fail=0; ok() { pass=$((pass+1)); echo "  ok   $1"; }; bad() { fail=$((fail+1)); echo "  FAIL $1"; }

cd "$T" && git init -q fx && cd fx && git config user.email t@x && git config user.name t
printf 'a\nb\nc\n' > f && git add f && git commit -q -m B0 && B0=$(git rev-parse HEAD)
git checkout -q -b feature && printf 'a\nB-feature\nc\n' > f && git commit -qam feature && FEAT=$(git rev-parse HEAD)
git checkout -q -B main "$B0" && printf 'a\nB-main\nc\n' > f && git commit -qam "main (conflicting)" && M1=$(git rev-parse HEAD)
printf 'a\nB-hand-resolved\nc\n' > f && git commit -qam "squash feature (#1), conflict resolved by hand" && S1=$(git rev-parse HEAD)

echo "1. conflict-resolution residual on a squash: the exact hunk, as a diff"
python3 "$CEB" --repo "$PWD" record --base "$M1" --reviewed-head "$FEAT" --merged "$S1" > "$T/r1.json"
python3 "$CEB" --repo "$PWD" verify "$T/r1.json" --json > "$T/v1.json"
python3 "$RENDER" "$T/v1.json" "$T/r1.json" --run-url https://example.test/run/1 > "$T/c1.md"
grep -q '^<!-- source-review-coverage -->$' "$T/c1.md" && ok "hidden marker present" || bad "marker missing"
grep -q '^### Source review coverage: `UNVERIFIED`' "$T/c1.md" && ok "verdict line" || bad "verdict line"
grep -q '^```diff$' "$T/c1.md" && ok "residual fenced as diff" || bad "no diff fence"
grep -q '^+B-hand-resolved$' "$T/c1.md" && grep -q '^-B-feature$' "$T/c1.md" && ok "the exact hunk: -B-feature / +B-hand-resolved" || bad "hunk missing"
grep -q '^-<<<<<<< ' "$T/c1.md" && ok "conflict markers shown as what the automatic merge produced" || bad "markers missing"
grep -q 'A pass establishes review coverage and nothing else' "$T/c1.md" && ok "§6 line present" || bad "§6 line missing"
grep -q 'No approvals are bound to this revision' "$T/c1.md" && ok "no-approvals note" || bad "no-approvals note missing"
grep -q 'https://example.test/run/1' "$T/c1.md" && ok "artifact link" || bad "artifact link missing"

echo "2. clean replay: silent by default, verdict table with --always"
git checkout -q -b feat2 "$B0" && printf 'a\nb\nc\nd\n' > f && git commit -qam feat2 && F2=$(git rev-parse HEAD)
git checkout -q -B main2 "$B0" && printf 'a0\na\nb\nc\n' > f && git commit -qam moved && M2=$(git rev-parse HEAD)
printf 'a0\na\nb\nc\nd\n' > f && git commit -qam "squash feat2 (#2)" && S2=$(git rev-parse HEAD)
python3 "$CEB" --repo "$PWD" record --base "$M2" --reviewed-head "$F2" --merged "$S2" --approver alice > "$T/r2.json"
python3 "$CEB" --repo "$PWD" verify "$T/r2.json" --json > "$T/v2.json"
python3 "$RENDER" "$T/v2.json" "$T/r2.json" > "$T/c2.md"
[ ! -s "$T/c2.md" ] && ok "no comment on a clean replay" || bad "comment rendered for a clean replay"
python3 "$RENDER" "$T/v2.json" "$T/r2.json" --always > "$T/c2a.md"
grep -q 'replay' "$T/c2a.md" && grep -q '| alice |' "$T/c2a.md" && ok "--always renders the verdict and the approvals table" || bad "--always output wrong"
grep -q '```diff' "$T/c2a.md" && bad "diff fence on a clean replay" || ok "no diff fence when there is no residual"

echo "3. approved-then-pushed: table names the approved revision; diff is the post-approval bytes"
python3 - "$T/ap3.json" "$F2" <<'PY'
import json, sys
json.dump([{"approver": "alice", "commit": sys.argv[2], "review_id": 7, "submitted_at": "2026-09-08T10:00:00Z", "state": "APPROVED", "source": "forge-api"}], open(sys.argv[1], "w"))
PY
git checkout -q feat2 && printf 'a\nb\nc\nd\ne\n' > f && git commit -qam "pushed after approval" && F3=$(git rev-parse HEAD)
git checkout -q main2 && git reset -q --hard "$M2" && printf 'a0\na\nb\nc\nd\ne\n' > f && git commit -qam "squash feat2 (#3)" && S3=$(git rev-parse HEAD)
python3 "$CEB" --repo "$PWD" record --base "$M2" --reviewed-head "$F2" --merged "$S3" --approvals "$T/ap3.json" > "$T/r3.json"
python3 "$CEB" --repo "$PWD" verify "$T/r3.json" --json > "$T/v3.json"
python3 "$RENDER" "$T/v3.json" "$T/r3.json" > "$T/c3.md"
grep -q "| alice | \`${F2:0:12}\` |" "$T/c3.md" && ok "table row names the approved revision" || bad "table row wrong: $(grep '| alice' "$T/c3.md")"
grep -q '^+e$' "$T/c3.md" && ! grep -q '^+d$' "$T/c3.md" && ok "diff is exactly the post-approval byte" || bad "diff content wrong"

echo "4. truncation"
python3 "$RENDER" "$T/v1.json" "$T/r1.json" --max-diff 40 > "$T/c4.md"
grep -q 'truncated at 40 characters' "$T/c4.md" && ok "long residual truncated with a note" || bad "truncation note missing"

echo; echo "passed $pass, failed $fail"
[ "$fail" = 0 ]
