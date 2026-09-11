#!/usr/bin/env bash
# The check run: rendered under the same residual/always/never rule as the
# comment, annotations placed on the shipped tree's line numbers, conclusion
# following fail-on (failure when failing, success only for VERIFIED, neutral
# otherwise), capped at the API's 50 annotations. Offline.
# Run: bash tests/check/test_render_check.sh
set -uo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CEB="$here/../../tools/ceb.py"; RENDER="$here/../../tools/render_check.py"
T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
pass=0; fail=0; ok() { pass=$((pass+1)); echo "  ok   $1"; }; bad() { fail=$((fail+1)); echo "  FAIL $1"; }
field() { python3 -c 'import json,sys; d=json.load(open(sys.argv[1]));
for k in sys.argv[2].split("."):
    d = d[int(k)] if k.lstrip("-").isdigit() else d[k]
print(d)' "$1" "$2"; }

cd "$T" && git init -q fx && cd fx && git config user.email t@x && git config user.name t
printf 'a\nb\nc\n' > f && git add f && git commit -q -m B0 && B0=$(git rev-parse HEAD)
git checkout -q -b feature && printf 'a\nB-feature\nc\n' > f && git commit -qam feature && FEAT=$(git rev-parse HEAD)
git checkout -q -B main "$B0" && printf 'a\nB-main\nc\n' > f && git commit -qam "main (conflicting)" && M1=$(git rev-parse HEAD)
printf 'a\nB-hand-resolved\nc\n' > f && git commit -qam "squash feature (#1), conflict resolved by hand" && S1=$(git rev-parse HEAD)

echo "1. conflict-resolution residual: annotation on the shipped line, neutral conclusion"
python3 "$CEB" --repo "$PWD" record --base "$M1" --reviewed-head "$FEAT" --merged "$S1" > "$T/r1.json"
python3 "$CEB" --repo "$PWD" verify "$T/r1.json" --json > "$T/v1.json"
python3 "$RENDER" "$T/v1.json" "$T/r1.json" --head-sha "$S1" --run-url https://example.test/run/1 > "$T/p1.json"
[ "$(field "$T/p1.json" name)" = source-review-coverage ] && ok "check name" || bad "name: $(field "$T/p1.json" name)"
[ "$(field "$T/p1.json" head_sha)" = "$S1" ] && ok "head_sha carried" || bad "head_sha wrong"
[ "$(field "$T/p1.json" conclusion)" = neutral ] && ok "conclusion neutral when not failing and not VERIFIED" || bad "conclusion: $(field "$T/p1.json" conclusion)"
[ "$(field "$T/p1.json" output.annotations.0.path)" = f ] && ok "annotation path is the file" || bad "path: $(field "$T/p1.json" output.annotations.0.path)"
[ "$(field "$T/p1.json" output.annotations.0.start_line)" = 2 ] && ok "annotation on line 2, the resolved hunk" || bad "start_line: $(field "$T/p1.json" output.annotations.0.start_line)"
[ "$(field "$T/p1.json" output.annotations.0.annotation_level)" = warning ] && ok "level warning when not failing" || bad "level wrong"
field "$T/p1.json" output.annotations.0.message | grep -q '+B-hand-resolved' && ok "message carries the exact hunk" || bad "hunk missing from message"
field "$T/p1.json" output.summary | grep -q 'A pass establishes review coverage and nothing else' && ok "§6 line in summary" || bad "§6 missing"
field "$T/p1.json" output.summary | grep -q 'source-review-coverage -->' && bad "comment marker leaked into summary" || ok "no comment marker in summary"

echo "2. --fail: conclusion failure, annotations at failure level"
python3 "$RENDER" "$T/v1.json" "$T/r1.json" --head-sha "$S1" --fail > "$T/p2.json"
[ "$(field "$T/p2.json" conclusion)" = failure ] && ok "conclusion failure" || bad "conclusion: $(field "$T/p2.json" conclusion)"
[ "$(field "$T/p2.json" output.annotations.0.annotation_level)" = failure ] && ok "annotation level failure" || bad "level wrong"

echo "3. clean replay: silent by default, --always renders with no annotations"
git checkout -q -b feat2 "$B0" && printf 'a\nb\nc\nd\n' > f && git commit -qam feat2 && F2=$(git rev-parse HEAD)
git checkout -q -B main2 "$B0" && printf 'a0\na\nb\nc\n' > f && git commit -qam moved && M2=$(git rev-parse HEAD)
printf 'a0\na\nb\nc\nd\n' > f && git commit -qam "squash feat2 (#2)" && S2=$(git rev-parse HEAD)
python3 "$CEB" --repo "$PWD" record --base "$M2" --reviewed-head "$F2" --merged "$S2" --approver alice > "$T/r2.json"
python3 "$CEB" --repo "$PWD" verify "$T/r2.json" --json > "$T/v2.json"
python3 "$RENDER" "$T/v2.json" "$T/r2.json" --head-sha "$S2" > "$T/p3.json"
[ ! -s "$T/p3.json" ] && ok "no check run on a clean replay" || bad "rendered for a clean replay"
python3 "$RENDER" "$T/v2.json" "$T/r2.json" --head-sha "$S2" --always > "$T/p3a.json"
[ -s "$T/p3a.json" ] && [ "$(python3 -c 'import json,sys; print(len(json.load(open(sys.argv[1]))["output"]["annotations"]))' "$T/p3a.json")" = 0 ] \
  && ok "--always renders the verdict with zero annotations" || bad "--always output wrong"

echo "4. VERIFIED is the only success; the cap is the API's 50"
python3 - "$T" <<'PY'
import json, sys
t = sys.argv[1]
diff = []
for i in range(60):
    diff += [f"diff --git a/f{i} b/f{i}", f"--- a/f{i}", f"+++ b/f{i}",
             "@@ -1,1 +1,1 @@", "-old", "+new"]
json.dump({"verdict": "VERIFIED", "steps": [], "residual": "\n".join(diff)}, open(f"{t}/v4.json", "w"))
json.dump({"change": {"tree_hash": "git-sha1:abc"}, "approvals": []}, open(f"{t}/r4.json", "w"))
PY
python3 "$RENDER" "$T/v4.json" "$T/r4.json" --head-sha deadbeef > "$T/p4.json"
[ "$(field "$T/p4.json" conclusion)" = success ] && ok "VERIFIED renders success" || bad "conclusion: $(field "$T/p4.json" conclusion)"
[ "$(python3 -c 'import json,sys; print(len(json.load(open(sys.argv[1]))["output"]["annotations"]))' "$T/p4.json")" = 50 ] \
  && ok "annotations capped at 50" || bad "cap not applied"
field "$T/p4.json" output.summary | grep -q '60 residual hunks; the first 50' && ok "summary names the truncation" || bad "truncation note missing"

echo; echo "passed $pass, failed $fail"
[ "$fail" = 0 ]
