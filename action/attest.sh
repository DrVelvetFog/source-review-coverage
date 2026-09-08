#!/usr/bin/env bash
# Source Review Coverage — the composite action's one script.
#
# Builds a record for the revision that just landed, re-expresses it as an
# in-toto Statement, signs it with the workflow's own identity (ambient OIDC,
# never a developer key — rule R4), verifies what it just signed, and reports.
#
# Everything here is driven by environment variables so the same script runs
# on a laptop with SRC_SIGN=false. See docs/action.md for the contract.
set -euo pipefail

: "${SRC_MODE:=auto}"                 # auto | push | pull_request
: "${SRC_FAIL_ON:=signature}"         # never | signature | residual
: "${SRC_SIGN:=true}"
: "${SRC_DECLARED_BY:=github-actions}"
: "${SRC_SIGSTORE_VERSION:=4.5.0}"
: "${SRC_REPO:=${GITHUB_WORKSPACE:-.}}"
: "${SRC_OUT:=${RUNNER_TEMP:-/tmp}/source-review-coverage}"
: "${SRC_SIGNER_REPO:=${GITHUB_REPOSITORY:-}}"
: "${GITHUB_OUTPUT:=/dev/null}"
: "${GITHUB_STEP_SUMMARY:=/dev/null}"
: "${GITHUB_EVENT_NAME:=push}"

case "$SRC_FAIL_ON" in
  never|signature|residual) ;;
  *) echo "::error::fail-on must be never, signature or residual (got '$SRC_FAIL_ON')"; exit 1 ;;
esac

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CEB="$here/../tools/ceb.py"
mkdir -p "$SRC_OUT"

out() { printf '%s=%s\n' "$1" "$2" >> "$GITHUB_OUTPUT"; }
note() { echo "::notice::$*"; }
warn() { echo "::warning::$*"; }
die()  { echo "::error::$*"; exit 1; }

out dir "$SRC_OUT"   # first, so a failed run still uploads whatever it produced

# ---- 1. which revision, which review state -------------------------------
mode="$SRC_MODE"
if [ "$mode" = auto ]; then
  case "$GITHUB_EVENT_NAME" in
    pull_request|pull_request_target) mode=pull_request ;;
    *) mode=push ;;
  esac
fi

if [ -n "${SRC_BASE:-}" ] && [ -n "${SRC_HEAD:-}" ]; then
  base="$SRC_BASE"; head="$SRC_HEAD"; merged="${SRC_MERGED:-HEAD}"
elif [ "$mode" = pull_request ]; then
  [ -n "${GITHUB_EVENT_PATH:-}" ] || die "pull_request mode needs GITHUB_EVENT_PATH"
  read -r base head < <(python3 - "$GITHUB_EVENT_PATH" <<'PY'
import json, sys
e = json.load(open(sys.argv[1]))["pull_request"]
print(e["base"]["sha"], e["head"]["sha"])
PY
)
  merged=HEAD   # actions/checkout gives the merge ref; its parents are base and head
else
  merged=HEAD; head=HEAD
  if git -C "$SRC_REPO" rev-parse --verify -q HEAD^ >/dev/null; then
    base=HEAD^
  else
    note "root commit: nothing to compare against, no record issued"
    out verdict SKIPPED; out dir "$SRC_OUT"; exit 0
  fi
fi
echo "mode=$mode base=$base reviewed-head=$head merged=$merged"

# ---- 2. record, statement -------------------------------------------------
python3 "$CEB" --repo "$SRC_REPO" record \
  --base "$base" --reviewed-head "$head" --merged "$merged" \
  --declared-by "$SRC_DECLARED_BY" > "$SRC_OUT/record.json"
python3 "$CEB" --repo "$SRC_REPO" intoto "$SRC_OUT/record.json" > "$SRC_OUT/statement.json"

# ---- 3. sign ----------------------------------------------------------------
verify_args=(--statement "$SRC_OUT/statement.json")
PY_SIG=python3   # the interpreter that has sigstore, when signing
if [ "$SRC_SIGN" = true ]; then
  # An isolated interpreter: the runner's system python carries a dist-packages
  # pyOpenSSL that breaks against the cryptography release pip installs, and
  # sigstore is the only package this action ever installs.
  venv="$SRC_OUT/venv"
  python3 -m venv "$venv"
  PY_SIG="$venv/bin/python"
  "$PY_SIG" -m pip install --quiet --disable-pip-version-check "sigstore==$SRC_SIGSTORE_VERSION"
  if ! "$PY_SIG" -m sigstore sign --bundle "$SRC_OUT/statement.sigstore.json" "$SRC_OUT/statement.json"; then
    die "signing failed (sigstore output above). If it mentions an identity token or OIDC, the job needs 'permissions: id-token: write' so the workflow identity can sign (rule R4)."
  fi
  verify_args+=(--bundle "$SRC_OUT/statement.sigstore.json" --signer-repo "$SRC_SIGNER_REPO")
else
  warn "sign=false: the record is an assertion, not evidence (R4); verdict can be at best INCOMPLETE"
fi

# ---- 4. verify what we just produced --------------------------------------
set +e
"$PY_SIG" "$CEB" --repo "$SRC_REPO" verify "$SRC_OUT/record.json" "${verify_args[@]}" --json > "$SRC_OUT/verify.json"
set -e

# ---- 5. outputs, summary, fail-on -----------------------------------------
eval "$(python3 - "$SRC_OUT" "$SRC_SIGN" "$SRC_FAIL_ON" <<'PY'
import json, sys, shlex
out, sign, fail_on = sys.argv[1], sys.argv[2] == "true", sys.argv[3]
v = json.load(open(f"{out}/verify.json"))
steps = {s["step"]: s for s in v["steps"]}
sig = steps.get("signatures", {}).get("status", "INCOMPLETE")
residual = v.get("residual")
if residual:
    open(f"{out}/residual.diff", "w").write(residual)
with open(f"{out}/summary.md", "w") as f:
    f.write(f"### Source review coverage — `{v['verdict']}`\n\n| step | status | detail |\n|---|---|---|\n")
    for s in v["steps"]:
        f.write(f"| {s['step']} | {s['status']} | {s['detail']} |\n")
    if residual:
        f.write("\n**Residual — bytes that shipped with no approval covering them:**\n\n```diff\n" + residual[:20000] + "\n```\n")
    f.write("\nA pass establishes review coverage. It does not establish correctness, that a human read anything, "
            "truthful authorship, reviewer independence, existence at a time, or compliance (spec §6).\n")
rc = 0
if fail_on == "signature":
    if sign and sig != "PASS": rc = 1
elif fail_on == "residual":
    if (sign and sig != "PASS") or residual: rc = 1
print(f"VERDICT={shlex.quote(v['verdict'])}; SIG={sig}; RESIDUAL={'1' if residual else '0'}; RC={rc}")
PY
)"

out verdict "$VERDICT"
out signatures "$SIG"
out record "$SRC_OUT/record.json"
out statement "$SRC_OUT/statement.json"
out bundle "$([ -f "$SRC_OUT/statement.sigstore.json" ] && echo "$SRC_OUT/statement.sigstore.json" || true)"
out residual "$([ "$RESIDUAL" = 1 ] && echo "$SRC_OUT/residual.diff" || true)"
out dir "$SRC_OUT"
cat "$SRC_OUT/summary.md" >> "$GITHUB_STEP_SUMMARY"

echo; python3 - "$SRC_OUT/verify.json" <<'PY'
import json, sys
v = json.load(open(sys.argv[1])); w = max(len(s["step"]) for s in v["steps"])
for s in v["steps"]:
    print(f"  {dict(PASS='✓',FAIL='✗',WARN='!',INCOMPLETE='?')[s['status']]} {s['step'].ljust(w)}  {s['status']:<10} {s['detail']}")
print(f"\n  VERDICT: {v['verdict']}")
PY

if [ "$RC" != 0 ]; then
  die "fail-on=$SRC_FAIL_ON: verdict '$VERDICT' (signatures $SIG, residual $RESIDUAL)"
fi
note "source review coverage: $VERDICT (signatures $SIG)"
