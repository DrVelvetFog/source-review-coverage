#!/usr/bin/env bash
# Release checks. Plain: the metadata every push must keep true. With --tag vX.Y.Z:
# everything a release needs before the tag is cut. Exit 1 on any FAIL.
#
#   bash tools/release_check.sh              # metadata lint (runs in CI as an example)
#   bash tools/release_check.sh --tag v0.3.0 # pre-tag: version, changelog, clean tree
set -u
cd "$(dirname "$0")/.."
TAG="${2:-}"; [ "${1:-}" = "--tag" ] || TAG=""
python3 - "$TAG" <<'PY'
import json, re, subprocess, sys
tag = sys.argv[1]
fails = 0
def res(ok, name, detail):
    global fails
    fails += 0 if ok else 1
    print(f"  {'✓' if ok else '✗'} {name:<28} {'PASS' if ok else 'FAIL':<5} {detail}")

a = open("action.yml").read()
m = re.search(r'^description:\s*"?(.*?)"?\s*$', a, re.M)
d = m.group(1) if m else ""
res(0 < len(d) <= 125, "action description", f"{len(d)} characters (Marketplace allows 125)")
res(re.search(r'^name:\s*\S', a, re.M) is not None, "action name", "present")
res(re.search(r'^branding:\n\s+icon:\s*\S+\n\s+color:\s*\S+', a, re.M) is not None, "action branding", "icon and color present")

version = open("VERSION").read().strip()
res(re.fullmatch(r"\d+\.\d+\.\d+", version) is not None, "VERSION", version)
cl = open("CHANGELOG.md").read()
heads = re.findall(r"^## \[(\d+\.\d+\.\d+)\] - (\d{4}-\d{2}-\d{2})", cl, re.M)
newest = heads[0][0] if heads else ""
unreleased = re.search(r"^## \[Unreleased\]\n(.*?)(?=^## \[)", cl, re.M | re.S)
pending = bool(unreleased and re.search(r"^- ", unreleased.group(1), re.M))
if tag:
    res(tag == "v" + version, "tag matches VERSION", f"{tag} vs VERSION {version}")
    res(newest == version, "changelog heading", f"newest entry is [{newest}]")
    res(not pending, "changelog unreleased", "empty" if not pending else "still has entries; move them under the version")
else:
    res(newest == version or pending, "changelog", f"newest entry [{newest}]" + (", unreleased entries pending" if pending else ""))

if tag:
    # Only before a tag: this script is itself an attested example, so reading
    # examples/attest.json on every push would check a file that is being rewritten.
    att = json.load(open("examples/attest.json"))
    vs = sorted({s["predicate"]["version"] for s in att["attestations"]})
    res(vs == [version], "examples attested against", ", ".join(vs) or "nothing")
    man = json.load(open("examples/manifest.json"))
    ids = {e["id"] for e in man["examples"]}
    have = {s["predicate"]["id"] for s in att["attestations"]}
    res(ids <= have, "examples attested", f"{len(ids & have)} of {len(ids)}")
    dirty = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True).stdout.strip()
    res(not dirty, "working tree", "clean" if not dirty else "uncommitted changes")
    exists = subprocess.run(["git", "rev-parse", "-q", "--verify", f"refs/tags/{tag}"], capture_output=True).returncode == 0
    res(not exists, "tag not yet cut", tag)

print(f"release check: {'PASS' if fails == 0 else 'FAIL'}" + (f" for {tag}" if tag else ""))
sys.exit(1 if fails else 0)
PY
