#!/usr/bin/env bash
# Offline walk-through: a pull request approved on one revision, pushed to once more,
# then squashed onto a base that moved. What does the verifier say, and what exactly
# does the residual contain? No network, no signing; Python 3 and git only.
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CEB="$here/../tools/ceb.py"
T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
cd "$T" && git init -q repo && cd repo
git config user.email you@example.com && git config user.name you

printf 'a\nb\nc\n' > f && git add f && git commit -q -m "base" && BASE=$(git rev-parse HEAD)
git checkout -q -b feature
printf 'a\nb\nc\nd\n' > f && git commit -qam "add d"      && APPROVED=$(git rev-parse HEAD)
printf 'a\nb\nc\nd\ne\n' > f && git commit -qam "add e"   && PUSHED_AFTER=$(git rev-parse HEAD)
git checkout -q "$BASE" && git checkout -q -B main
printf 'a0\na\nb\nc\n' > f && git commit -qam "main moves on"        && LANDING_BASE=$(git rev-parse HEAD)
printf 'a0\na\nb\nc\nd\ne\n' > f && git commit -qam "squash feature (#1)" && SHIPPED=$(git rev-parse HEAD)

# The forge's review data, as the action would read it: one approval, given on "add d".
cat > approvals.json <<JSON
[{"approver": "reviewer", "commit": "$APPROVED", "review_id": 1,
  "submitted_at": "2026-09-08T10:00:00Z", "state": "APPROVED", "source": "forge-api"}]
JSON

python3 "$CEB" --repo . record --base "$LANDING_BASE" --reviewed-head "$APPROVED" \
  --merged "$SHIPPED" --approvals approvals.json > record.json
python3 "$CEB" --repo . verify record.json --json > verify.json || true

python3 - <<'PY'
import json
v = json.load(open("verify.json"))
for s in v["steps"]:
    if s["step"] in ("merge transform", "approval binding"):
        print(f'{s["step"]}: {s["status"]} — {s["detail"].split(" (")[0]}')
print("residual:")
for line in (v["residual"] or "").splitlines():
    if line.startswith(("+", "-")) and not line.startswith(("+++", "---")):
        print("  " + line)
print("verdict:", v["verdict"])
PY
