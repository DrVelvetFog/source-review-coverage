#!/usr/bin/env python3
"""
ceb — Change-Evidence Binding, reference implementation of SPEC.md §5 / §5a.

Two subcommands:

  ceb.py record --base <ref> --reviewed-head <ref> --merged <ref> [--approver ...]
  ceb.py verify <record.json> [--json]
  ceb.py verify-artifact <dir> [--signer-repo owner/name] [--json]   # one call, read-only

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


def merge_tree(base, head, repo=".", extra=()):
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
    out, rc = git("merge-tree", "--write-tree", *extra, base_oid, head_oid, repo=repo, check=False)
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
    the commit. Octopus merges are folded left in recorded parent order, with
    rename detection off: native octopus does none, and a fold that detects
    renames reports CONFLICT (rename/rename) on merges octopus accepted cleanly
    (CE-012, experiments/octopus_probe.md). Two-parent merges keep rename
    detection, because that is what the forges' merge does.

    Note: this writes tree (and, for 3+ parents, commit) objects into the
    repository. They are unreferenced and get collected; a verifier that must
    not write should operate on a copy."""
    if len(parents) < 2:
        return (True, None)
    if len(parents) == 2:
        return merge_tree(parents[0], parents[1], repo=repo)

    acc, clean = parents[0], True
    for p in parents[1:]:
        ok, tree = merge_tree(acc, p, repo=repo, extra=("-X", "no-renames"))
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


def object_exists(oid, repo="."):
    _, rc = git("cat-file", "-e", f"{oid}^{{commit}}", repo=repo, check=False)
    return rc == 0


def approvals_for_record(args, *, fmt, reviewed, repo="."):
    """Approvals as the record carries them (rule R3: each bound to the tree it
    was given on).

    --approvals FILE takes what the forge reported: a list of
    {approver, commit, tree?, review_id?, submitted_at?}. The tree is resolved
    from the commit when that object is present locally (source "git"); when a
    reviewed revision was force-pushed away and only the forge still knows its
    tree, the forge's value is used and labelled (source "forge-api") so a
    verifier can tell which claims it could recompute.

    --approver NAME is the bare form: one approval over the reviewed head."""
    out = []
    if getattr(args, "approvals", None):
        for a in json.load(open(args.approvals)):
            commit = a.get("commit")
            if commit and object_exists(commit, repo=repo):
                tree, source = tree_of(commit, repo=repo), "git"
            elif a.get("tree"):
                tree, source = a["tree"], a.get("source", "forge-api")
            else:
                raise SystemExit(f"approval by {a.get('approver')} names neither a "
                                 "reachable commit nor a tree; refusing to guess")
            if a.get("tree") and source == "git" and a["tree"] != tree:
                raise SystemExit(f"approval by {a.get('approver')}: forge tree "
                                 f"{a['tree'][:12]} != git tree {tree[:12]} for {commit[:12]}")
            out.append({
                "over_tree_hash": f"git-{fmt}:{tree}",
                "approver": a.get("approver"),
                "commit": commit,
                "review_id": a.get("review_id"),
                "submitted_at": a.get("submitted_at"),
                "source": source,
                "signature": None,  # v0: unsigned, see verify_signatures
            })
    if getattr(args, "approver", None):
        out.append({
            "over_tree_hash": f"git-{fmt}:{reviewed}",
            "approver": args.approver,
            "commit": git("rev-parse", args.reviewed_head, repo=repo)[0],
            "review_id": None,
            "submitted_at": None,
            "source": "argument",
            "signature": None,
        })
    out.sort(key=lambda a: (a.get("submitted_at") or "", a.get("review_id") or 0))
    return out


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
        "approvals": approvals_for_record(args, fmt=fmt, reviewed=reviewed, repo=repo),
        "merge_transform": {
            "kind": transform_kind,
            # Only meaningful for a merge commit; a squash has one parent
            # and the field would imply a multi-parent replay that never happened.
            "parents": parents if len(parents) >= 2 else [],
            "reviewed_head": git("rev-parse", args.reviewed_head, repo=repo)[0],
            "base_at_merge": git("rev-parse", args.base, repo=repo)[0],
            "expected_tree": f"git-{fmt}:{expected}" if expected else None,
            "replay_clean": clean,
            "strategy": "ort -X no-renames" if len(parents) >= 3 else "ort",
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

    # 2. merge transform — is the shipped tree the automatic merge of the
    # reviewed head onto the base? This is a fact about the change, computed
    # whether or not anyone approved anything: bytes that are not the automatic
    # merge were produced at merge time and no review covered them by
    # construction. For a true merge commit the replay inputs come from the
    # object graph, not from the record: parents cannot be misreported without
    # changing the commit that is being verified. The record is only trusted
    # for a squash, where the reviewed head is no longer reachable from the merge.
    mt = record.get("merge_transform") or {}
    approvals = record.get("approvals", [])
    identity_approved = any(bare(a.get("over_tree_hash")) == shipped for a in approvals)

    graph_parents = parents_of(merged_ref, repo=repo) if merged_ref else []
    clean, expected, source = None, None, None
    if len(graph_parents) >= 2:
        clean, expected = replay_merge(graph_parents, repo=repo)
        source = f"{len(graph_parents)} parents, from the commit graph"
    elif mt.get("base_at_merge") and mt.get("reviewed_head"):
        clean, expected = merge_tree(mt["base_at_merge"], mt["reviewed_head"], repo=repo)
        source = "recorded squash inputs"
    recorded = bare(mt.get("expected_tree"))
    if recorded and expected and recorded != expected:
        res.add("replay drift", "WARN",
                f"recomputed {expected[:12]} != recorded {recorded[:12]} "
                f"(strategy/git_version differ?)")
    if expected is None:
        res.add("merge transform", "WARN",
                "no replay inputs; cannot tell whether the shipped tree is the automatic merge")
    elif expected == shipped:
        res.add("merge transform", "PASS",
                f"replay ({source}) — shipped is the automatic merge, exactly")
    else:
        why = ("evil merge: edits made inside the merge commit" if len(graph_parents) >= 2
               else "merge conflicted; resolved by hand" if not clean
               else "edited after the automatic merge")
        res.residual = diff_trees(expected, shipped, repo=repo)
        if identity_approved:
            # The shipped tree itself was approved, so the residual was seen.
            res.add("merge transform", "WARN",
                    f"shipped is not the automatic merge ({why}); the shipped tree was approved as such")
        else:
            res.add("merge transform", "FAIL",
                    f"residual — bytes shipped that are not the automatic merge of the reviewed head ({why})")

    # 2b. approval binding: does an approval cover the shipped tree? Directly
    # (identity), or because the shipped tree is exactly the automatic merge of
    # the revision that was approved onto the base it landed on (replay of the
    # approved revision, not of whatever was pushed afterwards). When it is
    # neither, the residual is the diff between that automatic merge and what
    # shipped: the bytes that landed beyond what the approver saw.
    landing_base = graph_parents[0] if len(graph_parents) >= 2 else mt.get("base_at_merge")
    reviewed_tree = None
    if mt.get("reviewed_head"):
        try:
            reviewed_tree = tree_of(mt["reviewed_head"], repo=repo)
        except RuntimeError:
            reviewed_tree = None
    # One approval that covers the shipped tree is coverage; an earlier approval
    # of a superseded revision is stale, not a failure. The failure is when no
    # approval covers, and then the residual is measured from the most recent
    # approval: the bytes that landed beyond what the last reviewer saw.
    covered, stale = False, []
    for a in approvals:
        over, who = bare(a.get("over_tree_hash")), a.get("approver") or "?"
        commit = a.get("commit")
        if over == shipped:
            res.add("approval binding", "PASS", f"identity — {who} approved the shipped tree")
            covered = True
        elif commit and landing_base and object_exists(commit, repo=repo):
            _, expected_a = merge_tree(landing_base, commit, repo=repo)
            if expected_a == shipped:
                res.add("approval binding", "PASS",
                        f"replay — shipped is the automatic merge of the revision {who} approved ({commit[:12]})")
                covered = True
            else:
                stale.append(("residual", who, commit, expected_a))
        elif reviewed_tree and over == reviewed_tree and expected == shipped:
            res.add("approval binding", "PASS",
                    f"replay ({source}) — shipped is the automatic merge of the reviewed head {who} approved")
            covered = True
        else:
            stale.append(("unreachable", who, commit or over, None))

    if not approvals:
        res.add("approval binding", "FAIL", "no approvals in record")
    elif covered:
        for kind, who, ref, _ in stale:
            res.add("approval", "WARN",
                    f"stale — {who}'s approval ({ref[:12]}) does not cover the shipped tree; a later approval does")
    else:
        kind, who, ref, expected_a = stale[-1]   # approvals are in submission order
        if kind == "residual":
            res.add("approval binding", "FAIL",
                    f"residual — bytes shipped beyond what {who} approved ({ref[:12]})")
            res.residual = diff_trees(expected_a, shipped, repo=repo) if expected_a else res.residual
        else:
            res.add("approval binding", "FAIL",
                    f"unreachable — the revision {who} approved ({ref[:12]}) is not in this repository; cannot replay")
            if not res.residual:
                res.residual = diff_trees(ref, shipped, repo=repo) or None
        for kind, who, ref, _ in stale[:-1]:
            res.add("approval", "WARN", f"stale — {who}'s approval ({ref[:12]}) does not cover the shipped tree")

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

    # statement binding: the signed statement must be exactly what this record
    # produces, coverage recomputed. A statement about the same tree with a
    # different claim (a better coverage result, a different approver) would
    # otherwise ride on a valid signature.
    if statement_path:
        try:
            given = json.load(open(statement_path))
            expected_stmt = to_intoto(record)
            result, residual_base = coverage_result(record, repo=repo, _res=res)
            expected_stmt["predicate"]["reviewCoverage"] = {"result": result}
            if residual_base:
                expected_stmt["predicate"]["reviewCoverage"]["residualBase"] = {
                    "digest": {"gitTree": residual_base}}
            if canonical(given) == canonical(expected_stmt):
                res.add("statement binding", "PASS", "statement is exactly what this record produces")
            else:
                res.add("statement binding", "FAIL",
                        "statement differs from what this record produces (edited, or made from another record)")
        except (OSError, ValueError) as e:
            res.add("statement binding", "FAIL", f"statement unreadable: {e}")

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
                {k: v for k, v in {
                    "overTree": tree(a.get("over_tree_hash")),
                    "approver": a.get("approver"),
                    # Asserted by the forge; bounds nothing without an inclusion proof.
                    "approvedAt": a.get("submitted_at"),
                }.items() if v is not None}
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


def coverage_result(record, repo=".", _res=None):
    """The headline field, derived from a real verification rather than asserted.

    Emitting a statement that claims coverage without having recomputed it
    would reproduce exactly the vendor-log problem this predicate exists to
    replace."""
    res = _res if _res is not None else verify(record, repo=repo)
    binding = [(st, d) for step, st, d in res.steps if step == "approval binding"]
    if any(st == "PASS" and d.startswith("identity") for st, d in binding):
        return "identity", None
    if any(st == "PASS" and d.startswith("replay") for st, d in binding):
        return "replay", None
    if any(st == "FAIL" and d.startswith("residual") for st, d in binding):
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


class ReadOnlyRepo:
    """Replay writes tree objects (SPEC §5c note). A verifier that must not
    touch the repository it is given replays in a throwaway bare clone that
    borrows the original's objects (git's alternates) and receives the new
    ones itself. Nothing is written to the source; the clone is deleted."""

    def __init__(self, repo, allow_write=False):
        self.repo, self.allow_write, self.tmp = repo, allow_write, None

    def __enter__(self):
        if self.allow_write:
            return self.repo
        import tempfile
        self.tmp = tempfile.mkdtemp(prefix="srcv-")
        r = subprocess.run(["git", "clone", "--quiet", "--bare", "--shared", self.repo, self.tmp],
                           capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError(f"could not make a read-only clone: {r.stderr.strip()}")
        return self.tmp

    def __exit__(self, *exc):
        if self.tmp:
            import shutil
            shutil.rmtree(self.tmp, ignore_errors=True)


EXIT_VERIFIED, EXIT_UNVERIFIED, EXIT_INCOMPLETE, EXIT_MALFORMED = 0, 1, 2, 3


def cmd_verify_artifact(args):
    """Everything a consumer needs, in one call: the record's claims recomputed
    against the repository, the signature checked and bound to a workflow
    identity, and the statement checked to be exactly what the record produces.

    Exit codes: 0 verified · 1 unverified (a residual, no covering approval,
    or a failed signature — the report names which) · 2 incomplete (a claim
    could not be checked, typically signatures) · 3 malformed input."""
    import os
    d = args.dir
    paths = {k: os.path.join(d, f) for k, f in
             (("record", "record.json"), ("statement", "statement.json"),
              ("bundle", "statement.sigstore.json"))}
    if not os.path.isfile(paths["record"]):
        print(f"malformed: {paths['record']} not found", file=sys.stderr)
        return EXIT_MALFORMED
    try:
        record = json.load(open(paths["record"]))
        for k in ("change", "record_digest"):
            if k not in record:
                raise ValueError(f"record lacks '{k}'")
        bare(record["change"]["tree_hash"])
    except (ValueError, KeyError, TypeError) as e:
        print(f"malformed: record.json: {e}", file=sys.stderr)
        return EXIT_MALFORMED
    statement_path = paths["statement"] if os.path.isfile(paths["statement"]) else None
    bundle_path = paths["bundle"] if os.path.isfile(paths["bundle"]) else None
    if statement_path:
        try:
            json.load(open(statement_path))
        except ValueError as e:
            print(f"malformed: statement.json: {e}", file=sys.stderr)
            return EXIT_MALFORMED

    try:
        with ReadOnlyRepo(args.repo, allow_write=args.allow_write) as repo:
            res = verify(record, repo=repo, bundle_path=bundle_path,
                         signer_repo=args.signer_repo, statement_path=statement_path)
    except RuntimeError as e:
        print(f"malformed: {e}", file=sys.stderr)
        return EXIT_MALFORMED
    if not bundle_path:
        res.add("bundle", "INCOMPLETE", "no statement.sigstore.json in the artifact")

    worst = res.worst
    code = {"PASS": EXIT_VERIFIED, "WARN": EXIT_VERIFIED,
            "INCOMPLETE": EXIT_INCOMPLETE, "FAIL": EXIT_UNVERIFIED}[worst]
    if args.json:
        json.dump({"schema": SCHEMA, "verdict": VERDICTS[worst], "worst": worst,
                   "exit": code, "read_only": not args.allow_write,
                   "steps": [{"step": st, "status": status, "detail": detail}
                             for st, status, detail in res.steps],
                   "residual": res.residual}, sys.stdout, indent=2)
        print()
        return code
    width = max(len(s_[0]) for s_ in res.steps)
    for step, status, detail in res.steps:
        mark = {"PASS": "✓", "FAIL": "✗", "WARN": "!", "INCOMPLETE": "?"}[status]
        print(f"  {mark} {step.ljust(width)}  {status:<10} {detail}")
    if res.residual:
        print("\n  residual — shipped without an approval covering it:")
        for line in res.residual.splitlines():
            if line.startswith(("+", "-")) and not line.startswith(("+++", "---")):
                print(f"      {line}")
    print(f"\n  VERDICT: {VERDICTS[worst]}   (exit {code}, "
          f"{'in place' if args.allow_write else 'read-only replay'})")
    return code


VERDICTS = {
    "FAIL": "UNVERIFIED",
    # Never claim VERIFIED while any claim went unchecked (SPEC §6).
    "INCOMPLETE": "INCOMPLETE — signatures not checked; this is not a verification",
    "WARN": "VERIFIED (with warnings)",
    "PASS": "VERIFIED",
}


def cmd_verify(args):
    record = json.load(open(args.record))
    res = verify(record, repo=args.repo, bundle_path=args.bundle,
                 signer_repo=args.signer_repo, statement_path=args.statement)
    worst = res.worst

    if args.json:
        # Machine-readable form for automation (the GitHub Action reads this).
        # Same content as the report below, same exit code; nothing is decided
        # here that the human report would not show.
        json.dump({
            "schema": SCHEMA,
            "verdict": VERDICTS[worst],
            "worst": worst,
            "steps": [{"step": st, "status": status, "detail": detail}
                      for st, status, detail in res.steps],
            "residual": res.residual,
        }, sys.stdout, indent=2)
        print()
        return 1 if worst == "FAIL" else 0

    width = max(len(s[0]) for s in res.steps)
    for step, status, detail in res.steps:
        mark = {"PASS": "✓", "FAIL": "✗", "WARN": "!", "INCOMPLETE": "?"}[status]
        print(f"  {mark} {step.ljust(width)}  {status:<10} {detail}")

    if res.residual:
        print("\n  residual — shipped without an approval covering it:")
        for line in res.residual.splitlines():
            if line.startswith(("+", "-")) and not line.startswith(("+++", "---")):
                print(f"      {line}")

    print(f"\n  VERDICT: {VERDICTS[worst]}")
    return 1 if worst == "FAIL" else 0


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--repo", default=".")
    sub = p.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("record")
    r.add_argument("--base", required=True)
    r.add_argument("--reviewed-head", required=True)
    r.add_argument("--merged", required=True)
    r.add_argument("--approver", help="one approval over the reviewed head (bare form)")
    r.add_argument("--approvals", help="JSON file of forge-reported approvals, each bound to its own revision")
    r.add_argument("--check", action="append")
    r.add_argument("--agent", action="append")
    r.add_argument("--declared-by")
    r.set_defaults(func=cmd_record)

    v = sub.add_parser("verify")
    v.add_argument("record")
    v.add_argument("--bundle", help="Sigstore bundle over the in-toto Statement")
    v.add_argument("--signer-repo", help="owner/name whose workflow must have signed (R4)")
    v.add_argument("--statement", help="the signed in-toto Statement, when the bundle is detached")
    v.add_argument("--json", action="store_true",
                   help="emit the result as JSON instead of the human report (same exit code)")
    v.set_defaults(func=cmd_verify)

    va = sub.add_parser("verify-artifact",
                        help="verify a downloaded attestation artifact in one call (read-only)")
    va.add_argument("dir", help="directory holding record.json, statement.json, statement.sigstore.json")
    va.add_argument("--signer-repo", help="owner/name whose workflow must have signed (R4)")
    va.add_argument("--allow-write", action="store_true",
                    help="replay in the given repository instead of a throwaway clone")
    va.add_argument("--json", action="store_true")
    va.set_defaults(func=cmd_verify_artifact)

    i = sub.add_parser("intoto", help="re-express a record as an in-toto Statement")
    i.add_argument("record")
    i.set_defaults(func=cmd_intoto)

    args = p.parse_args()
    sys.exit(args.func(args) or 0)


if __name__ == "__main__":
    main()
