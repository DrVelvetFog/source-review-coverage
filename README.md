# Source Review Coverage

Evidence, recomputable by a stranger, that the code which shipped is the code a human
approved. One line in a workflow; a signed [in-toto](https://github.com/in-toto/attestation)
attestation for every revision that lands.

```yaml
# .github/workflows/attest.yml
name: attest
on:
  push:
    branches: [main]
  pull_request:
  pull_request_review:
    types: [submitted]
permissions:
  contents: read
  id-token: write        # lets the workflow identity sign
  pull-requests: read    # lets the action read reviews
jobs:
  attest:
    runs-on: ubuntu-latest
    steps:
      - uses: DrVelvetFog/source-review-coverage@v1
```

That is the whole file. The action checks the repository out with full history itself.

## What you get on the first merge

For every revision that lands, an artifact containing the record, the in-toto statement,
a Sigstore bundle signed by *this workflow in this repository* (never a developer's key),
and, when it applies, `residual.diff`: the exact bytes that shipped with no approval
covering them. Plus a job summary:

| step | status | detail |
|---|---|---|
| change integrity | PASS | tree `1bf9b504…` |
| merge transform | PASS | replay — shipped is the automatic merge, exactly |
| approval binding | PASS | replay — shipped is the automatic merge of the revision `jku` approved (`c06358e5`) |
| signatures | PASS | verified, signed by the workflow of `sigstore/sigstore-python` |

That row is real: a maintainer's approval on one revision, replayed onto the squash that
landed six weeks later on a base that had moved, reproduces the shipped tree exactly.

Approvals come from the pull request's reviews, read with the workflow's own token, each
bound to the tree of the revision it was given on. A pull request approved and then pushed
to before merging yields `UNVERIFIED` with a residual naming the post-approval bytes. A
direct push to `main` has no approval and says so. Details, inputs and outputs:
[docs/action.md](docs/action.md).

## Checking it somewhere else

```bash
gh run download <run-id> -n source-review-coverage-attestation -D att
python tools/ceb.py verify att/record.json --statement att/statement.json \
    --bundle att/statement.sigstore.json --signer-repo owner/name
```

Python 3 and `git`; `pip install sigstore` for the signature check. The replay needs no
network. Without `sigstore` the verifier reports `INCOMPLETE` rather than passing an
unchecked claim. A runnable, offline walk-through is
[examples/quickstart.sh](examples/quickstart.sh); its execution is attested in
[examples/attest.json](examples/attest.json) so an agent can check it instead of recalling it.

## What a pass does not establish

Review coverage, and only that. Not correctness. Not that a human read anything. Not
truthful authorship. Not reviewer independence. Not existence at a stated time. And not
compliance with any regulation: a record may be evidence submitted toward an obligation,
never a certificate of meeting one. Specification §6 is the authority.

## The predicate

**Type URI:** `https://drvelvetfog.github.io/source-review-coverage/v0.1` ·
[Specification (v0.1)](v0.1/index.md) · [Protobuf definition](v0.1/source_review_coverage.proto)

SLSA v1.2 Source Track Level 4 requires that changes to protected branches be agreed to by
two or more trusted persons, and requires this of *the final revision submitted*. That
requirement has no verifier: SLSA leaves source provenance attestations undefined, and does
not address how squash merges or rebases interact with approval. So the property is asserted
by the same system that performed the merge, to a consumer who cannot check it.

This predicate replaces the assertion with something recomputable — which tree each approval
covered, which tree shipped, and how one became the other. Where they cannot be reconciled,
a verifier emits the specific bytes that shipped with no approval covering them. Measured
against 810 production merges across three repositories, every merge was explained as
identity or replay, with zero false positives (specification, Appendix A).

## Status

Predicate v0.1 submitted to the in-toto attestation framework as
[in-toto/attestation#581](https://github.com/in-toto/attestation/pull/581), under review.
Action `v1` tracks the latest `0.x` release; see [CHANGELOG.md](CHANGELOG.md). Plan and
backlog: [PLANS/V1](PLANS/V1/HORIZON_BRIEF.md). Maintenance runs on a fortnightly
release train, funded by [GitHub Sponsors](https://github.com/sponsors/DrVelvetFog).

Apache-2.0.
