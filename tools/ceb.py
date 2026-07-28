#!/usr/bin/env python3
"""
ceb — Change-Evidence Binding, reference implementation of SPEC.md §5 / §5a.

Two subcommands:

  ceb.py record --base <ref> --reviewed-head <ref> --merged <ref> [--approver ...]
  ceb.py verify <record.json>

The verifier assumes it trusts nobody: it is given a repository and a record,
and it recomputes. No network, no vendor API, no third-party packages. If a
claim cannot be recomputed, the tool says so rather than passing it through —
see the note on signatures in `verify_signatures`.
"""

import argparse
import hashlib
import json
import subprocess
import sys

SCHEMA = "change-evidence/v0"


# --------------------------------------------------------------------------
# git plumbing


def git(*args, repo=".", check=True):
    r = subprocess.run(
        ["git", "-C", repo, *args], capture_output=True, text=True
    )
    if check and r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {r.stderr.strip()}")
    return r.stdout.strip(), r.returncode


def object_format(repo="."):
    """Git repos are sha1 by default and sha256 only if created that way. The
    record must not claim 'sha256:' over a sha1 object — see verify output."""
    out, rc = git("rev-parse", "--show-object-format", repo=repo, check=False)
    return out if rc == 0 and out else "sha1"


def tree_of(rev, repo="."):
    out, _ = git("rev-parse", f"{rev}^{{tree}}", repo=repo)
    return out


def git_version(repo="."):
    out, _ = git("--version", repo=repo)
    return out.replace("git version ", "").split()[0]


def merge_tree(base, head, repo="."):
    """Replay: the merge the forge performed, computed without a worktree.

    Inputs are resolved to object IDs first, and that is load-bearing rather
    than tidy. When a merge conflicts, git writes conflict markers into the
    file and those markers contain *the names it was given* — so passing branch
    names yields a different blob, and therefore a different tree, than passing
    the commits they point at. A replay driven by ref names is not reproducible.

    Returns (clean: bool, tree: str|None). A non-zero exit means conflict, which
    is not an error here — it is the finding (SPEC §5a)."""
    base_oid, _ = git("rev-parse", base, repo=repo)
    head_oid, _ = git("rev-parse", head, repo=repo)
    out, rc = git("merge-tree", "--write-tree", base_oid, head_oid, repo=repo, check=False)
    first = out.splitlines()[0] if out else ""
    return (rc == 0, first or None)


def parents_of(rev, repo="."):
    """Parents in the order the commit records them. Order is load-bearing:
    for a clean merge the replay is symmetric, but once it conflicts the
    markers embed the sides and (P1,P2) != (P2,P1). Measured, not assumed."""
    out, _ = git("rev-list", "--parents", "-n", "1", rev, repo=repo)
    return out.split()[1:]


def replay_merge(parents, repo="."):
    """Replay a true merge commit from its own parents.

    A merge commit carries its replay inputs in the object graph, so unlike a
    squash it needs nothing recorded alongside it — the verifier reads them off
    the commit. Octopus merges are folded left in recorded parent order.

    Note: this writes tree (and, for 3+ parents, commit) objects into the
    repository. They are unreferenced and get collected; a verifier that must
    not write should operate on a copy."""
    if len(parents) < 2:
        return (True, None)
    if len(parents) == 2:
        return merge_tree(parents[0], parents[1], repo=repo)

    acc, clean = parents[0], True
    for p in parents[1:]:
        ok, tree = merge_tree(acc, p, repo=repo)
        clean = clean and ok
        if not tree:
            return (False, None)
        acc, _ = git("commit-tree", tree, "-p", acc, "-m", "replay", repo=repo)
    return (clean, tree_of(acc, repo=repo))


def diff_trees(a, b, repo="."):
    out, _ = git("diff", "--no-color", a, b, repo=repo, check=False)
    return out


# --------------------------------------------------------------------------
# canonicalisation


def canonical(obj):
    """RFC 8785 (JCS) subset: sorted keys, no insignificant whitespace, UTF-8.

    Sufficient for the field types this schema uses (strings, ints, bools,
    objects, arrays). Full JCS also pins float serialisation; this record type
    has no floats, and a conforming implementation MUST reject them rather than
    guess — hence the explicit check."""
    def no_floats(o):
        if isinstance(o, float):
            raise ValueError("floats are not canonicalisable under this subset")
        if isinstance(o, dict):
            for v in o.values():
                no_floats(v)
        if isinstance(o, list):
            for v in o:
                no_floats(v)

    no_floats(obj)
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def digest(obj):
    return "sha256:" + hashlib.sha256(canonical(obj).encode()).hexdigest()


# --------------------------------------------------------------------------
# record


def cmd_record(args):
    repo = args.repo
    fmt = object_format(repo)
    shipped = tree_of(args.merged, repo=repo)
    reviewed = tree_of(args.reviewed_head, repo=repo)
    base = tree_of(args.base, repo=repo)

    parents = parents_of(args.merged, repo=repo)
    if len(parents) >= 2:
        # A true merge commit. Its parents ARE the replay inputs, so the record
        # describes rather than supplies them — a verifier reads them off git.
        clean, expected = replay_merge(parents, repo=repo)
        transform_kind = "merge_commit"
    else:
        clean, expected = merge_tree(args.base, args.reviewed_head, repo=repo)
        transform_kind = "squash"

    record = {
        "schema": SCHEMA,
        "object_format": fmt,  # what the tree hashes actually are
        "change": {
            "tree_hash": f"git-{fmt}:{shipped}",
            "parent_tree_hash": f"git-{fmt}:{base}",
            "locators": {
                # Resolved, not as typed: a digest field must carry a digest,
                # and a ref is a name (R1). The spelling is kept beside it.
                "merged": git("rev-parse", args.merged, repo=repo)[0],
                "merged_ref": args.merged,
                "reviewed_head": git("rev-parse", args.reviewed_head, repo=repo)[0],
                "base": git("rev-parse", args.base, repo=repo)[0],
            },
        },
        "authorship": {
            "declared_by": args.declared_by or "unset",
            "agents": [{"tool": t} for t in (args.agent or [])],
        },
        "checks": [
            {"name": c, "over_tree_hash": f"git-{fmt}:{reviewed}", "outcome": "pass"}
            for c in (args.check or [])
        ],
        "approvals": (
            [
                {
                    "over_tree_hash": f"git-{fmt}:{reviewed}",
                    "approver": args.approver,
                    "signature": None,  # v0: unsigned, see verify_signatures
                }
            ]
            if args.approver
            else []
        ),
        "merge_transform": {
            "kind": transform_kind,
            # Only meaningful for a merge commit; a squash has one parent
            # and the field would imply a multi-parent replay that never happened.
            "parents": parents if len(parents) >= 2 else [],
            "reviewed_head": git("rev-parse", args.reviewed_head, repo=repo)[0],
            "base_at_merge": git("rev-parse", args.base, repo=repo)[0],
            "expected_tree": f"git-{fmt}:{expected}" if expected else None,
            "replay_clean": clean,
            "strategy": "ort",
            "git_version": git_version(repo),
        },
    }
    record["record_digest"] = digest(
        {k: v for k, v in record.items() if k != "record_digest"}
    )
    json.dump(record, sys.stdout, indent=2)
    print()


# --------------------------------------------------------------------------
# verification (SPEC §5)


def bare(h):
    """Strip the 'git-sha1:' / 'sha256:' prefix from a recorded hash."""
    return h.split(":", 1)[1] if h and ":" in h else h


class Result:
    def __init__(self):
        self.steps = []
        self.residual = None

    def add(self, step, status, detail=""):
        self.steps.append((step, status, detail))

    @property
    def worst(self):
        order = ["FAIL", "INCOMPLETE", "WARN", "PASS"]
        for level in order:
            if any(s[1] == level for s in self.steps):
                return level
        return "PASS"


DSSE_PAYLOAD_TYPE = "application/vnd.in-toto+json"


def dsse_pae(payload_type, payload):
    """DSSE Pre-Authentication Encoding.

    The signature covers this, not the raw JSON, so that a payload cannot be
    reinterpreted under a different type. Stdlib — no dependency needed to
    understand what was signed."""
    return b"DSSEv1 %d %s %d %s" % (
        len(payload_type), payload_type.encode(), len(payload), payload
    )


def verify_bundle(bundle_path, res, statement_path=None, signer_repo=None,
                  signer_issuer=None):
    """Verify a Sigstore bundle over an in-toto Statement.

    Offline against the bundle's own material: the certificate chains to
    Fulcio, the entry carries its transparency-log inclusion proof, and the
    signature covers the DSSE PAE. What it does NOT establish is anything about
    the signer's honesty — only key custody, byte integrity, and which workflow
    identity held the key (SPEC §6).

    R4 is the reason the identity check is not optional: a record signed by the
    party being audited is an assertion. Binding to a workflow identity is what
    makes it evidence."""
    try:
        from sigstore.models import Bundle
        from sigstore.verify import Verifier, policy
    except ImportError:
        res.add("signatures", "INCOMPLETE",
                "sigstore not installed; install the 'sigstore' package to check signatures")
        return None

    try:
        bundle = Bundle.from_json(open(bundle_path, "rb").read())
    except Exception as e:
        res.add("signatures", "FAIL", f"bundle unreadable: {e}")
        return None

    if signer_repo:
        pol = policy.AllOf([
            policy.OIDCSourceRepositoryURI(f"https://github.com/{signer_repo}"),
            policy.OIDCIssuer(signer_issuer or "https://token.actions.githubusercontent.com"),
        ])
        who = f"workflow of {signer_repo}"
    else:
        # Without an expected signer the signature is checkable but says nothing
        # about who stood behind it — which is the whole point of R4.
        pol = policy.UnsafeNoOp()
        who = "unpinned signer"

    # Two envelope shapes, because the toolchain forces it. sigstore-python
    # validates in-toto Statements against a DigestSet of sha256/384/512 and
    # sha3 only, and rejects any other key — including `gitCommit` and
    # `gitTree`, which the in-toto attestation spec itself defines. A statement
    # whose subject names a git object therefore cannot be carried in a DSSE
    # envelope by that library, so it is signed as an artifact instead: the
    # signature is over the exact statement bytes rather than over a typed
    # payload. Same key custody, same identity binding, one less layer of
    # typing. Try DSSE first so this reverts by itself once upstream allows it.
    verifier = Verifier.production()
    statement = None
    try:
        payload_type, payload = verifier.verify_dsse(bundle, pol)
        if payload_type != DSSE_PAYLOAD_TYPE:
            res.add("signatures", "FAIL", f"unexpected payload type {payload_type}")
            return None
        statement = json.loads(payload)
        shape = "DSSE"
    except Exception as dsse_err:
        if not statement_path:
            res.add("signatures", "FAIL", f"signature verification failed: {dsse_err}")
            return None
        try:
            raw = open(statement_path, "rb").read()
            verifier.verify_artifact(raw, bundle, pol)
            statement = json.loads(raw)
            shape = "detached over the statement bytes"
        except Exception as e:
            res.add("signatures", "FAIL", f"signature verification failed: {e}")
            return None

    if signer_repo:
        res.add("signatures", "PASS", f"verified ({shape}), signed by the {who}")
    else:
        res.add("signatures", "INCOMPLETE",
                "signature valid but signer not pinned — pass --signer-repo to bind it (R4)")
    return statement


def verify_signatures(record, res, bundle_path=None, signer_repo=None,
                      statement_path=None):
    """An unsigned record is an assertion, not evidence (R4)."""
    if bundle_path:
        return verify_bundle(bundle_path, res, statement_path=statement_path,
                             signer_repo=signer_repo)
    res.add("signatures", "INCOMPLETE", "no bundle supplied; record is an assertion (R4)")
    return None


def verify(record, repo=".", bundle_path=None, signer_repo=None,
           statement_path=None):
    res = Result()
    fmt = record.get("object_format", "sha1")
    change = record["change"]
    shipped = bare(change["tree_hash"])

    # 1. change integrity — does the recorded shipped tree exist as recorded?
    merged_ref = change.get("locators", {}).get("merged")
    if merged_ref:
        try:
            actual = tree_of(merged_ref, repo=repo)
            if actual == shipped:
                res.add("change integrity", "PASS", f"tree {shipped[:12]}")
            else:
                res.add("change integrity", "FAIL", f"recorded {shipped[:12]} != actual {actual[:12]}")
                return res
        except RuntimeError:
            # R1: refs are locators. Losing one is drift, not failure.
            res.add("locator drift", "WARN", f"'{merged_ref}' no longer resolves")
    else:
        res.add("change integrity", "WARN", "no locator to resolve against")

    # 2/5a. approval binding, with replay when the base moved
    mt = record.get("merge_transform") or {}
    approvals = record.get("approvals", [])
    # Whether the reviewed state was shown to cover the shipped state. Check
    # coverage depends on this: if unreviewed bytes shipped, a check that ran
    # over the reviewed tree did not test what shipped either.
    covered = False
    if not approvals:
        res.add("approval binding", "FAIL", "no approvals in record")
    for a in approvals:
        over = bare(a.get("over_tree_hash"))
        if over == shipped:
            res.add("approval binding", "PASS", "identity — approved tree is the shipped tree")
            covered = True
            continue

        # The approved tree is not the shipped tree. Replay before failing.
        #
        # For a true merge commit the replay inputs come from the object graph,
        # not from the record: parents cannot be misreported without changing
        # the commit that is being verified. The record is only trusted for a
        # squash, where the reviewed head is no longer reachable from the merge.
        graph_parents = parents_of(merged_ref, repo=repo) if merged_ref else []
        if len(graph_parents) >= 2:
            clean, expected = replay_merge(graph_parents, repo=repo)
            source = f"{len(graph_parents)} parents, from the commit graph"
        else:
            base, head = mt.get("base_at_merge"), mt.get("reviewed_head")
            if not (base and head):
                res.add("approval binding", "FAIL", "tree mismatch and no merge_transform to replay")
                continue
            clean, expected = merge_tree(base, head, repo=repo)
            source = "recorded squash inputs"
        recorded = bare(mt.get("expected_tree"))
        if recorded and expected and recorded != expected:
            res.add("replay drift", "WARN",
                    f"recomputed {expected[:12]} != recorded {recorded[:12]} "
                    f"(strategy/git_version differ?)")
        if expected == shipped:
            res.add("approval binding", "PASS", f"replay ({source}) — shipped is the automatic merge, exactly")
            covered = True
        else:
            detail = "residual — bytes shipped that no approval covers"
            if len(graph_parents) >= 2:
                detail += " (evil merge: edits made inside the merge commit)"
            elif not clean:
                detail += " (merge conflicted)"
            res.add("approval binding", "FAIL", detail)
            if expected:
                res.residual = diff_trees(expected, shipped, repo=repo)

    # 3. check coverage
    #
    # A check over the reviewed tree only speaks for the shipped tree if the
    # review was shown to cover it. Where residual bytes shipped, the checks
    # never ran over those bytes either — reporting them as passing would be
    # the exact promise-shaped claim this tool exists to refuse.
    for c in record.get("checks", []):
        over = bare(c.get("over_tree_hash"))
        if over == shipped:
            ok, why = c.get("outcome") == "pass", "over the shipped tree"
        elif covered and mt.get("reviewed_head") and over == tree_of(mt["reviewed_head"], repo=repo):
            ok, why = c.get("outcome") == "pass", "over the reviewed tree, which replay covers"
        else:
            ok, why = False, "ran over a tree no approval covers"
        res.add(f"check:{c.get('name')}", "PASS" if ok else "FAIL", why)

    # 4. signatures
    signed_statement = verify_signatures(record, res, bundle_path=bundle_path,
                                         signer_repo=signer_repo,
                                         statement_path=statement_path)
    if signed_statement is not None:
        # The signature covers a Statement; check it is a statement about the
        # same tree this record describes, or the signature is over something
        # else entirely.
        subj = (signed_statement.get("subject") or [{}])[0].get("digest", {})
        if subj.get("gitTree") != shipped:
            res.add("signature subject", "FAIL",
                    "the signed statement is about a different tree")
        else:
            res.add("signature subject", "PASS", "signed statement covers this tree")

    # digest integrity of the record itself
    stated = record.get("record_digest")
    if stated:
        recomputed = digest({k: v for k, v in record.items() if k != "record_digest"})
        res.add("record digest", "PASS" if recomputed == stated else "FAIL",
                "" if recomputed == stated else "record was edited after issuance")

    if fmt == "sha1":
        res.add("object format", "WARN",
                "repository is sha1; tree hashes are not collision-resistant to a "
                "motivated attacker (git sha256 repos avoid this)")
    return res


def to_intoto(record, subject_name="refs/heads/main"):
    """Re-express a record as an in-toto Statement (see PREDICATE.md).

    Same claims, framework-native shape: gitCommit/gitTree are first-class
    digest types here, so the tree the approval covers — the whole point — is
    expressible without inventing an encoding."""
    mt = record.get("merge_transform") or {}
    fmt = record.get("object_format", "sha1")
    loc = record["change"].get("locators", {})

    def tree(h):
        # in-toto nests digests under a `digest` key (cf. ResourceDescriptor,
        # and the VSA predicate's Policy message) rather than inlining them.
        return {"digest": {"gitTree": bare(h)}} if h else None

    def commit(h):
        return {"digest": {"gitCommit": h}} if h else None

    return {
        "_type": "https://in-toto.io/Statement/v1",
        "subject": [{
            "name": subject_name,
            "digest": {
                "gitCommit": loc.get("merged", ""),
                "gitTree": bare(record["change"]["tree_hash"]),
            },
        }],
        "predicateType": "https://drvelvetfog.github.io/source-review-coverage/v0.1",
        "predicate": {
            "approvals": [
                {"overTree": tree(a.get("over_tree_hash")), "approver": a.get("approver")}
                for a in record.get("approvals", [])
            ],
            "checks": [
                {"name": c.get("name"), "overTree": tree(c.get("over_tree_hash")),
                 "outcome": c.get("outcome")}
                for c in record.get("checks", [])
            ],
            "mergeTransform": {
                "kind": {"squash": "squash", "merge_commit": "mergeCommit"}.get(
                    mt.get("kind"), mt.get("kind")),
                "reviewedHead": commit(mt.get("reviewed_head")),
                "baseAtMerge": commit(mt.get("base_at_merge")),
                "parents": [commit(p) for p in mt.get("parents", [])],
                "expectedTree": tree(mt.get("expected_tree")),
                "replayClean": mt.get("replay_clean"),
                "strategy": mt.get("strategy"),
                "gitVersion": mt.get("git_version"),
            },
            "authorship": {
                "declaredBy": record.get("authorship", {}).get("declared_by"),
                "agents": record.get("authorship", {}).get("agents", []),
            },
            "objectFormat": fmt,
        },
    }


def coverage_result(record, repo="."):
    """The headline field, derived from a real verification rather than asserted.

    Emitting a statement that claims coverage without having recomputed it
    would reproduce exactly the vendor-log problem this predicate exists to
    replace."""
    res = verify(record, repo=repo)
    for step, status, detail in res.steps:
        if step != "approval binding":
            continue
        if status == "PASS" and "identity" in detail:
            return "identity", None
        if status == "PASS" and "replay" in detail:
            return "replay", None
        if status == "FAIL" and "residual" in detail:
            mt = record.get("merge_transform") or {}
            return "residual", bare(mt.get("expected_tree"))
    return "unverifiable", None


def cmd_intoto(args):
    record = json.load(open(args.record))
    result, residual_base = coverage_result(record, repo=args.repo)
    stmt = to_intoto(record)
    stmt["predicate"]["reviewCoverage"] = {"result": result}
    if residual_base:
        stmt["predicate"]["reviewCoverage"]["residualBase"] = {
            "digest": {"gitTree": residual_base}
        }
    json.dump(stmt, sys.stdout, indent=2)
    print()


def cmd_verify(args):
    record = json.load(open(args.record))
    res = verify(record, repo=args.repo, bundle_path=args.bundle,
                 signer_repo=args.signer_repo, statement_path=args.statement)

    width = max(len(s[0]) for s in res.steps)
    for step, status, detail in res.steps:
        mark = {"PASS": "✓", "FAIL": "✗", "WARN": "!", "INCOMPLETE": "?"}[status]
        print(f"  {mark} {step.ljust(width)}  {status:<10} {detail}")

    if res.residual:
        print("\n  residual — shipped without an approval covering it:")
        for line in res.residual.splitlines():
            if line.startswith(("+", "-")) and not line.startswith(("+++", "---")):
                print(f"      {line}")

    worst = res.worst
    verdict = {
        "FAIL": "UNVERIFIED",
        # Never claim VERIFIED while any claim went unchecked (SPEC §6).
        "INCOMPLETE": "INCOMPLETE — signatures not checked; this is not a verification",
        "WARN": "VERIFIED (with warnings)",
        "PASS": "VERIFIED",
    }[worst]
    print(f"\n  VERDICT: {verdict}")
    return 1 if worst == "FAIL" else 0


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--repo", default=".")
    sub = p.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("record")
    r.add_argument("--base", required=True)
    r.add_argument("--reviewed-head", required=True)
    r.add_argument("--merged", required=True)
    r.add_argument("--approver")
    r.add_argument("--check", action="append")
    r.add_argument("--agent", action="append")
    r.add_argument("--declared-by")
    r.set_defaults(func=cmd_record)

    v = sub.add_parser("verify")
    v.add_argument("record")
    v.add_argument("--bundle", help="Sigstore bundle over the in-toto Statement")
    v.add_argument("--signer-repo", help="owner/name whose workflow must have signed (R4)")
    v.add_argument("--statement", help="the signed in-toto Statement, when the bundle is detached")
    v.set_defaults(func=cmd_verify)

    i = sub.add_parser("intoto", help="re-express a record as an in-toto Statement")
    i.add_argument("record")
    i.set_defaults(func=cmd_intoto)

    args = p.parse_args()
    sys.exit(args.func(args) or 0)


if __name__ == "__main__":
    main()
