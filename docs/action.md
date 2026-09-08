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
permissions:
  contents: read
  id-token: write        # lets the workflow identity sign (rule R4)
  pull-requests: read
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

and a job summary with the same table. Until approvals are sourced from the forge's
review data (CE-002), a push to `main` carries no approval and the coverage verdict is
`UNVERIFIED`; the signature is what this version can prove, and it does.

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

## Outputs

`verdict`, `signatures`, `residual` (path or empty), `record`, `statement`, `bundle`.

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
