#!/usr/bin/env bash
# verify-artifact: one call, read-only, distinct named failures, exit codes.
# Run: bash tests/verify/test_verify_artifact.sh   (no network; the signature
# check runs only when the `sigstore` package is importable)
set -uo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$here/../.."
CEB="$ROOT/tools/ceb.py"
FIX="$here/fixtures/74db64e"        # a real artifact signed by this repository's workflow
T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
pass=0; fail=0
ok()  { pass=$((pass+1)); echo "  ok   $1"; }
bad() { fail=$((fail+1)); echo "  FAIL $1"; }
step() { python3 -c 'import json,sys; v=json.load(open(sys.argv[1])); print(next((s["status"]+" "+s["detail"] for s in v["steps"] if s["step"]==sys.argv[2]), "absent"))' "$1" "$2"; }
have_sigstore=$(python3 -c 'import sigstore' 2>/dev/null && echo yes || echo no)

echo "1. the real signed artifact against this repository (read-only)"
before=$(git -C "$ROOT" count-objects -v | awk '/^count/{print $2}')
python3 "$CEB" --repo "$ROOT" verify-artifact "$FIX" --signer-repo DrVelvetFog/source-review-coverage --json > "$T/v1.json"; rc=$?
after=$(git -C "$ROOT" count-objects -v | awk '/^count/{print $2}')
[ "$before" = "$after" ] && ok "repository untouched (loose objects $before → $after)" || bad "repository written to ($before → $after)"
step "$T/v1.json" "change integrity"  | grep -q '^PASS' && ok "change integrity" || bad "$(step "$T/v1.json" "change integrity")"
step "$T/v1.json" "merge transform"   | grep -q '^PASS' && ok "merge transform replays from the graph" || bad "$(step "$T/v1.json" "merge transform")"
step "$T/v1.json" "statement binding" | grep -q '^PASS' && ok "statement is what the record produces" || bad "$(step "$T/v1.json" "statement binding")"
if [ "$have_sigstore" = yes ]; then
  step "$T/v1.json" "signatures" | grep -q '^PASS' && ok "signature bound to the workflow" || bad "$(step "$T/v1.json" "signatures")"
  [ "$rc" = 1 ] && ok "exit 1: unverified — no approvals on a direct push (the report says so)" || bad "exit $rc"
else
  step "$T/v1.json" "signatures" | grep -q '^INCOMPLETE' && ok "sigstore absent → signatures INCOMPLETE, not passed" || bad "$(step "$T/v1.json" "signatures")"
fi

echo "2. tamper with each file: a distinct, named failure"
cp -r "$FIX" "$T/a" && python3 - "$T/a/record.json" <<'PY'
import json, sys; r = json.load(open(sys.argv[1])); r["authorship"]["declared_by"] = "someone-else"; json.dump(r, open(sys.argv[1], "w"))
PY
python3 "$CEB" --repo "$ROOT" verify-artifact "$T/a" --signer-repo DrVelvetFog/source-review-coverage --json > "$T/v2a.json"
step "$T/v2a.json" "record digest" | grep -q '^FAIL' && ok "record edited → record digest FAIL" || bad "$(step "$T/v2a.json" "record digest")"
step "$T/v2a.json" "statement binding" | grep -q '^FAIL' && ok "record edited → statement no longer what the record produces" || bad "$(step "$T/v2a.json" "statement binding")"
cp -r "$FIX" "$T/b" && sed -i.bak 's/"gitTree"/"gitTrEe"/' "$T/b/statement.json" && rm -f "$T/b/statement.json.bak"
python3 "$CEB" --repo "$ROOT" verify-artifact "$T/b" --signer-repo DrVelvetFog/source-review-coverage --json > "$T/v2b.json"
step "$T/v2b.json" "statement binding" | grep -q '^FAIL' && ok "statement edited → statement binding FAIL" || bad "$(step "$T/v2b.json" "statement binding")"
[ "$have_sigstore" = yes ] && { step "$T/v2b.json" "signatures" | grep -q '^FAIL' && ok "statement edited → signature FAIL" || bad "$(step "$T/v2b.json" "signatures")"; }
cp -r "$FIX" "$T/c" && printf '{"not":"a bundle"}' > "$T/c/statement.sigstore.json"
python3 "$CEB" --repo "$ROOT" verify-artifact "$T/c" --signer-repo DrVelvetFog/source-review-coverage --json > "$T/v2c.json"
[ "$have_sigstore" = yes ] && { step "$T/v2c.json" "signatures" | grep -q '^FAIL bundle unreadable' && ok "bundle edited → bundle unreadable" || bad "$(step "$T/v2c.json" "signatures")"; }

echo "3. exit codes"
mkdir -p "$T/empty"; python3 "$CEB" --repo "$ROOT" verify-artifact "$T/empty" >/dev/null 2>&1; [ $? = 3 ] && ok "missing record.json → exit 3" || bad "expected 3"
mkdir -p "$T/badjson"; echo '{' > "$T/badjson/record.json"; python3 "$CEB" --repo "$ROOT" verify-artifact "$T/badjson" >/dev/null 2>&1; [ $? = 3 ] && ok "malformed record.json → exit 3" || bad "expected 3"
cp -r "$FIX" "$T/d" && rm "$T/d/statement.sigstore.json"
python3 "$CEB" --repo "$ROOT" verify-artifact "$T/d" --signer-repo DrVelvetFog/source-review-coverage >/dev/null 2>&1; rc=$?
# no bundle: the worst status is FAIL (no approvals) which outranks INCOMPLETE — so 1; the bundle line still says INCOMPLETE
[ "$rc" = 1 ] && ok "no bundle + no approvals → exit 1 (FAIL outranks INCOMPLETE)" || bad "expected 1, got $rc"
{ python3 "$CEB" --repo "$ROOT" verify-artifact "$T/d" --signer-repo DrVelvetFog/source-review-coverage --json || true; } | python3 -c 'import json,sys; v=json.load(sys.stdin); sys.exit(0 if any(s["step"]=="bundle" and s["status"]=="INCOMPLETE" for s in v["steps"]) else 1)' && ok "missing bundle is named as INCOMPLETE" || bad "bundle line missing"

echo "4. incomplete: an approved, unsigned record"
cd "$T" && git init -q fx && cd fx && git config user.email t@x && git config user.name t
printf 'a\n' > f && git add f && git commit -q -m B && B=$(git rev-parse HEAD)
git checkout -q -b pr && printf 'a\nb\n' > f && git commit -qam A && A=$(git rev-parse HEAD)
git checkout -q -B main "$B" && printf 'a\nb\n' > f && git commit -qam "squash (#1)" && S=$(git rev-parse HEAD)
mkdir -p "$T/e" && python3 "$CEB" --repo "$PWD" record --base "$B" --reviewed-head "$A" --merged "$S" --approver alice > "$T/e/record.json" && python3 "$CEB" --repo "$PWD" intoto "$T/e/record.json" > "$T/e/statement.json"
python3 "$CEB" --repo "$PWD" verify-artifact "$T/e" > "$T/v4.txt" 2>&1; rc=$?
[ "$rc" = 2 ] && ok "approved but unsigned → exit 2 INCOMPLETE" || { bad "expected 2, got $rc"; cat "$T/v4.txt"; }
grep -q 'read-only replay' "$T/v4.txt" && ok "report says read-only replay" || bad "read-only note missing"
python3 "$CEB" --repo "$PWD" verify-artifact "$T/e" --allow-write > /dev/null 2>&1; [ $? = 2 ] && ok "--allow-write gives the same verdict in place" || bad "--allow-write differs"

echo; echo "passed $pass, failed $fail (sigstore: $have_sigstore)"
[ "$fail" = 0 ]
