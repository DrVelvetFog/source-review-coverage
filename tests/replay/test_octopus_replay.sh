#!/usr/bin/env bash
# CE-019: an octopus merge whose parents rename one path two different ways.
# Native octopus does no rename detection and merges it cleanly; a rename-
# detecting fold reports CONFLICT (rename/rename) and a different tree — a
# false residual. The verifier's ≥3-parent fold now runs -X no-renames, so
# this fixture must replay to the identical tree. Run:
#   bash tests/replay/test_octopus_replay.sh
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CEB="$here/../../tools/ceb.py"
T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
pass=0; fail=0
ok()   { pass=$((pass+1)); echo "  ok   $1"; }
bad()  { fail=$((fail+1)); echo "  FAIL $1"; }

# --- fixture: base has f.txt; br1 renames it to a.txt, br2 to b.txt ----------
cd "$T" && git init -q fx && cd fx && git config user.email t@x && git config user.name t
printf 'one\ntwo\nthree\n' > f.txt && printf 'g\n' > g.txt
git add . && git commit -q -m B0 && B0=$(git rev-parse HEAD)
git checkout -q -b br1 && git mv f.txt a.txt && git commit -q -m "rename f to a"
git checkout -q -b br2 "$B0" && git mv f.txt b.txt && git commit -q -m "rename f to b"
git checkout -q -B main "$B0" && printf 'h\n' > h.txt && git add h.txt && git commit -q -m M1
M1=$(git rev-parse HEAD)

echo "1. native octopus accepts the merge cleanly"
if git merge -q --no-edit br1 br2 >/dev/null 2>&1; then ok "git merge br1 br2 clean"; else bad "native octopus refused the fixture"; fi
MERGE=$(git rev-parse HEAD); SHIPPED=$(git rev-parse 'HEAD^{tree}')
[ "$(git rev-list --parents -n 1 HEAD | wc -w)" -eq 4 ] && ok "merge has 3 parents" || bad "not an octopus merge"

echo "2. a rename-detecting fold conflicts on the same input (the CE-012 shape)"
t1=$(git merge-tree --write-tree "$M1" br1 | head -1)
c1=$(git commit-tree "$t1" -p "$M1" -m replay)
if git merge-tree --write-tree "$c1" br2 >/dev/null 2>&1; then
  bad "rename-detecting fold merged cleanly; fixture lost its shape"
else ok "fold with renames reports a conflict, as the probe found"; fi

echo "3. the verifier's fold replays the identical tree"
python3 "$CEB" --repo "$PWD" record --base "$M1" --reviewed-head br2 --merged "$MERGE" > "$T/r.json"
python3 - "$T/r.json" "$SHIPPED" <<'PY' && ok "record: replay clean, expected == shipped, strategy recorded" || bad "record disagrees (see r.json)"
import json, sys
mt = json.load(open(sys.argv[1]))["merge_transform"]
assert mt["replay_clean"] is True, mt
assert mt["expected_tree"].split(":", 1)[1] == sys.argv[2], mt
assert mt["strategy"] == "ort -X no-renames", mt
PY

echo "4. verify: merge transform PASS, no residual"
{ python3 "$CEB" --repo "$PWD" verify "$T/r.json" --json || true; } > "$T/v.json"
python3 - "$T/v.json" <<'PY' && ok "merge transform PASS, residual empty" || bad "verify reported a residual (see v.json)"
import json, sys
v = json.load(open(sys.argv[1]))
step = next(s for s in v["steps"] if s["step"] == "merge transform")
assert step["status"] == "PASS", step
assert not v["residual"], v["residual"][:200]
PY

echo; echo "passed $pass, failed $fail"
[ "$fail" = 0 ]
