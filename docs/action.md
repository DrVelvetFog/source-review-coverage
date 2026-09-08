# The GitHub Action

One line in a workflow. For every revision that lands, the action records which tree
each approval covered, which tree shipped, and how one became the other; re-expresses
that as an in-toto Statement; signs it with the workflow's own identity; verifies what it
just signed; and uploads the three files so anyone can recompute the result offline.

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
  id-token: write        # lets the workflow identity sign (rule R4)
  pull-requests: write   # read reviews; post the one comment (read is enough with comment: never)
jobs:
  attest:
    runs-on: ubuntu-latest
    steps:
      - uses: DrVelvetFog/source-review-coverage@v1
```

That is the whole file. The action checks the repository out with full history itself
(replay needs history, not a shallow clone), so no other steps are required.

## What you get on the first merge

An artifact named `source-review-coverage-attestation` containing:

| file | what it is |
|---|---|
| `record.json` | the record: shipped tree, base tree, approvals, merge transform, replay result |
| `statement.json` | the same, as an in-toto Statement with predicate type `…/source-review-coverage/v0.1` |
| `statement.sigstore.json` | the Sigstore bundle: keyless signature bound to *this workflow in this repository* |
| `verify.json` | the verifier's own result over what it produced |
| `residual.diff` | only when bytes shipped that no approval covers: exactly those bytes |

and a job summary with the same table.

## Where approvals come from

The action reads the pull request's reviews with the workflow's own token
(`pull-requests: read`); it never accepts a personal token. A user's most recent review
counts when its state is `APPROVED`; a later change request or a dismissal by the same
user supersedes an earlier approval, as the forge itself treats it. Each approval is
bound to the tree of the revision it was given on (rule R3), and the reviewed head
becomes the most recently approved revision, so the replay measures exactly what landed
beyond what a reviewer saw.

- On `pull_request` and `pull_request_review` events, the approvals are the PR's own.
  Add `pull_request_review: types: [submitted]` to the workflow so the check re-runs when
  a review lands.
- On a push to `main`, the action asks the forge which merged pull request produced the
  commit, fetches `refs/pull/N/head` so approved revisions can be replayed, and binds
  that PR's approvals. A direct push has no pull request and therefore no approvals:
  the verdict is `UNVERIFIED`, which is the truth about it.
- A pull request approved and then pushed to before merging yields `UNVERIFIED` with a
  residual naming the post-approval bytes. An approved revision that was force-pushed
  away and can no longer be fetched is reported as unreachable and fails closed.
- Pull requests from forks have no signing identity; the action records without signing
  and says so.

## The comment

When bytes shipped that no approval covers, the action posts one comment on the pull
request: the verdict, each approval and the revision it was given on, and the residual as
a diff — the exact lines to review, since no review covered them by construction. On
re-runs the same comment is edited, found by a hidden marker, so a pull request never
accumulates a thread of status posts. Clean replays and identities stay silent unless
`comment: always`. Every comment ends with the specification's §6 line.

## Inputs

| input | default | meaning |
|---|---|---|
| `mode` | `auto` | `push` records `HEAD` against `HEAD^`; `pull_request` records the PR head against its base, with the merge ref as what shipped. `auto` picks from the event. |
| `fail-on` | `signature` | `never`: annotate only. `signature`: fail if the bundle does not verify. `residual`: additionally fail when bytes shipped with no approval covering them. A *missing* approval is reported, not failed. |
| `sign` | `true` | Sign with the workflow identity. `false` makes the record an assertion (R4) and caps the verdict at `INCOMPLETE`. |
| `upload` | `true` | Upload the artifact. |
| `checkout` | `true` | Check out inside the action. Set `false` if a previous step already did (with `fetch-depth: 0`). |
| `declared-by` | `github-actions` | Recorded as the party asserting authorship. Issuer-asserted; the verifier never treats it as verified. |
| `sigstore-version` | `4.5.0` | Pinned `sigstore` release used to sign and to check the signature. The only package installed. |
| `artifact-name` | `source-review-coverage-attestation` | Artifact name. |
| `approvals` | `auto` | `auto` reads the pull request's reviews with the workflow token; `off` records none. |
| `comment` | `residual` | One comment on the pull request, edited on re-runs rather than repeated. `residual` posts only when bytes shipped that no approval covers, with the diff; `always` posts the verdict on every run; `never`. Needs `pull-requests: write`; without it the comment is rendered into the artifact and a warning says why it was not posted. |

## Outputs

`verdict`, `signatures`, `residual` (path or empty), `record`, `statement`, `bundle`, `pr`
(the pull request the approvals came from), `approvals` (how many effective approvals),
`comment` (URL of the pull request comment, when one was posted).

## Verifying it somewhere else

```bash
gh run download <run-id> -n source-review-coverage-attestation -D att
python tools/ceb.py verify att/record.json --statement att/statement.json \
    --bundle att/statement.sigstore.json --signer-repo owner/name
```

Python 3 and `git`; `pip install sigstore` for the signature check. No network is needed
for the replay. Without the `sigstore` package the verifier reports `INCOMPLETE` rather
than passing an unchecked claim.

## What a pass does not establish

Review coverage, and only that. Not correctness, not that a human read anything, not
truthful authorship, not reviewer independence, not existence at a time, and not
compliance with anything. Specification §6 is the authority; this page inherits it.
