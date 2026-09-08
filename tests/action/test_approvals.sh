#!/usr/bin/env bash
# Approval binding, end to end, with no network: fixtures built with git, the
# forge's review data stood in for by a JSON file, and the verifier's own
# `--json` output asserted. Run: bash tests/action/test_approvals.sh
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CEB="$here/../../tools/ceb.py"
T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
pass=0; fail=0
ok()   { pass=$((pass+1)); echo "  ok   $1"; }
bad()  { fail=$((fail+1)); echo "  FAIL $1"; }

# --- fixture: base B0; PR branch A1 -> A2; main moves to M1 -------------------
cd "$T" && git init -q fx && cd fx && git config user.email t@x && git config user.name t
printf 'a\nb\nc\n' > f && git add f && git commit -q -m B0 && B0=$(git rev-parse HEAD)
git checkout -q -b pr
printf 'a\nb\nc\nd\n' > f && git commit -qam A1 && A1=$(git rev-parse HEAD)
printf 'a\nb\nc\nd\ne\n' > f && git commit -qam A2 && A2=$(git rev-parse HEAD)
git checkout -q -b main "$B0" 2>/dev/null || git checkout -q "$B0"
printf 'a0\na\nb\nc\n' > f && git commit -qam M1 && M1=$(git rev-parse HEAD)

approvals() {  # $1=file, then pairs approver:commit
  local f=$1; shift; python3 - "$f" "$@" <<'PY'
import json, sys
out = []
for i, pair in enumerate(sys.argv[2:]):
    who, commit = pair.split(":")
    out.append({"approver": who, "commit": commit, "review_id": 100 + i,
                "submitted_at": f"2026-09-08T10:0{i}:00Z", "state": "APPROVED", "source": "forge-api"})
json.dump(out, open(sys.argv[1], "w"))
PY
}
result() {  # $1=record -> coverage result from the emitter (recomputed, never asserted)
  python3 "$CEB" --repo "$PWD" intoto "$1" | python3 -c 'import json,sys; print(json.load(sys.stdin)["predicate"]["reviewCoverage"]["result"])'
}
step() {   # $1=record $2=step-name -> "STATUS detail"
  { python3 "$CEB" --repo "$PWD" verify "$1" --json || true; } | python3 -c '
import json,sys; v=json.load(sys.stdin)
for s in v["steps"]:
    if s["step"]==sys.argv[1]: print(s["status"], s["detail"]); break
print("RESIDUAL:" + ("yes" if v["residual"] else "no"))' "$2"
}

echo "1. identity: approval on A2, squash onto an unmoved base"
git checkout -q "$B0" && git checkout -q -b s1 && printf 'a\nb\nc\nd\ne\n' > f && git commit -qam "squash A2 (#1)" && S1=$(git rev-parse HEAD)
approvals "$T/ap1.json" "alice:$A2"
python3 "$CEB" --repo "$PWD" record --base "$B0" --reviewed-head "$A2" --merged "$S1" --approvals "$T/ap1.json" > "$T/r1.json"
[ "$(result "$T/r1.json")" = identity ] && ok "coverage=identity" || bad "coverage=$(result "$T/r1.json")"
step "$T/r1.json" "approval binding" | grep -q '^PASS identity' && ok "approval binding PASS identity" || bad "approval binding: $(step "$T/r1.json" "approval binding")"

echo "2. replay: approval on A2, squash onto the moved base M1 (clean)"
git checkout -q "$M1" && git checkout -q -b s2 && printf 'a0\na\nb\nc\nd\ne\n' > f && git commit -qam "squash A2 (#2)" && S2=$(git rev-parse HEAD)
approvals "$T/ap2.json" "alice:$A2"
python3 "$CEB" --repo "$PWD" record --base "$M1" --reviewed-head "$A2" --merged "$S2" --approvals "$T/ap2.json" > "$T/r2.json"
[ "$(result "$T/r2.json")" = replay ] && ok "coverage=replay" || bad "coverage=$(result "$T/r2.json")"
step "$T/r2.json" "approval binding" | grep -q 'RESIDUAL:no' && ok "no residual" || bad "unexpected residual"

echo "3. approved, then pushed, then merged: approval on A1, A2 landed"
approvals "$T/ap3.json" "alice:$A1"
python3 "$CEB" --repo "$PWD" record --base "$M1" --reviewed-head "$A1" --merged "$S2" --approvals "$T/ap3.json" > "$T/r3.json"
[ "$(result "$T/r3.json")" = residual ] && ok "coverage=residual" || bad "coverage=$(result "$T/r3.json")"
step "$T/r3.json" "approval binding" | grep -q '^FAIL residual — bytes shipped beyond what alice approved' && ok "residual names the approver" || bad "$(step "$T/r3.json" "approval binding")"
{ python3 "$CEB" --repo "$PWD" verify "$T/r3.json" --json || true; } | python3 -c 'import json,sys; r=json.load(sys.stdin)["residual"] or ""; sys.exit(0 if "+e" in r and "+d" not in r else 1)' \
  && ok "residual is exactly the post-approval byte (+e), not the approved one (+d)" || bad "residual content wrong"

echo "4. two approvals, the later one covers: alice on A1, bob on A2"
approvals "$T/ap4.json" "alice:$A1" "bob:$A2"
python3 "$CEB" --repo "$PWD" record --base "$M1" --reviewed-head "$A2" --merged "$S2" --approvals "$T/ap4.json" > "$T/r4.json"
[ "$(result "$T/r4.json")" = replay ] && ok "coverage=replay (bob's approval covers)" || bad "coverage=$(result "$T/r4.json")"
n=$({ python3 "$CEB" --repo "$PWD" verify "$T/r4.json" --json || true; } | python3 -c 'import json,sys; v=json.load(sys.stdin); print(sum(1 for s in v["steps"] if s["step"] in ("approval binding","approval")))')
[ "$n" = 2 ] && ok "both approvals reported (one covering, one stale)" || bad "expected 2 approval lines, got $n"
{ python3 "$CEB" --repo "$PWD" verify "$T/r4.json" --json || true; } | python3 -c 'import json,sys; v=json.load(sys.stdin); sys.exit(0 if v["residual"] is None and any(s["status"]=="WARN" and s["detail"].startswith("stale") for s in v["steps"]) else 1)' \
  && ok "stale approval is a WARN and no residual is reported" || bad "stale approval mishandled"

echo "5. approved revision force-pushed away: only the forge's tree is known"
TREE_A1=$(git rev-parse "$A1^{tree}")
python3 - "$T/ap5.json" "$TREE_A1" <<'PY'
import json, sys
json.dump([{"approver": "alice", "commit": "f" * 40, "tree": sys.argv[2], "review_id": 1, "submitted_at": "2026-09-08T10:00:00Z", "state": "APPROVED", "source": "forge-api"}], open(sys.argv[1], "w"))
PY
python3 "$CEB" --repo "$PWD" record --base "$M1" --reviewed-head "$A2" --merged "$S2" --approvals "$T/ap5.json" > "$T/r5.json"
grep -q '"source": "forge-api"' "$T/r5.json" && ok "record labels the forge-sourced tree" || bad "source label missing"
step "$T/r5.json" "approval binding" | grep -q '^FAIL unreachable' && ok "unreachable revision fails closed" || bad "$(step "$T/r5.json" "approval binding")"
[ "$(result "$T/r5.json")" = unverifiable ] && ok "coverage=unverifiable (not residual)" || bad "coverage=$(result "$T/r5.json")"

echo "6. true merge commit: approval on A2, merged into M1"
git checkout -q "$M1" && git checkout -q -b m6 && git merge -q --no-ff -m "Merge pull request #6" "$A2" && M6=$(git rev-parse HEAD)
approvals "$T/ap6.json" "alice:$A2"
python3 "$CEB" --repo "$PWD" record --base "$M1" --reviewed-head "$A2" --merged "$M6" --approvals "$T/ap6.json" > "$T/r6.json"
[ "$(result "$T/r6.json")" = replay ] && ok "coverage=replay from the merge commit's parents" || bad "coverage=$(result "$T/r6.json")"

echo "7. forge tree disagrees with git: refuse"
python3 - "$T/ap7.json" "$A2" <<'PY'
import json, sys
json.dump([{"approver": "alice", "commit": sys.argv[2], "tree": "0"*40, "review_id": 1, "submitted_at": "2026-09-08T10:00:00Z", "state": "APPROVED"}], open(sys.argv[1], "w"))
PY
if python3 "$CEB" --repo "$PWD" record --base "$M1" --reviewed-head "$A2" --merged "$S2" --approvals "$T/ap7.json" > /dev/null 2>"$T/err7"; then bad "record accepted a forge tree that contradicts git"; else grep -q 'forge tree' "$T/err7" && ok "record refuses a contradicting forge tree" || bad "wrong error: $(cat "$T/err7")"; fi

echo "8. --approver bare form still works (over the reviewed head)"
python3 "$CEB" --repo "$PWD" record --base "$M1" --reviewed-head "$A2" --merged "$S2" --approver carol > "$T/r8.json"
[ "$(result "$T/r8.json")" = replay ] && ok "bare --approver: replay" || bad "coverage=$(result "$T/r8.json")"

echo; echo "passed $pass, failed $fail"
[ "$fail" = 0 ]
