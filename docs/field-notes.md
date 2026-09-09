# Field notes: the first three repositories

What happened when the action was installed on three repositories that are not this one
(CE-006). All three are the author's own; none has a second reviewer, so every verdict
below is `UNVERIFIED` and correctly so. The point of the exercise was the install, the
first run, and whether a stranger can recompute what the run produced.

## The three

| repository | installed | first pull-request run | first push-to-`main` run | recomputed offline |
|---|---|---|---|---|
| [reversible](https://github.com/DrVelvetFog/reversible) | 2026-09-08, direct push, `@main` then `@v1` | none (direct push) | [34232524498](https://github.com/DrVelvetFog/reversible/actions/runs/34232524498): `pr=none`, replay from recorded squash inputs PASS, signatures PASS | yes, 2026-09-08 |
| [evidence-tier](https://github.com/DrVelvetFog/evidence-tier) | 2026-09-09, [PR #1](https://github.com/DrVelvetFog/evidence-tier/pull/1) merged as `66b70b7` | [34346716167](https://github.com/DrVelvetFog/evidence-tier/actions/runs/34346716167): replay (2 parents, from the graph) PASS, signatures PASS | [34346851886](https://github.com/DrVelvetFog/evidence-tier/actions/runs/34346851886): `pr=1` discovered from the merge commit, replay PASS, signatures PASS | yes, exit 1, read-only |
| [verified-examples](https://github.com/DrVelvetFog/verified-examples) | 2026-09-09, [PR #1](https://github.com/DrVelvetFog/verified-examples/pull/1) merged as `96f88ab` | [34346719156](https://github.com/DrVelvetFog/verified-examples/actions/runs/34346719156): same | [34346864122](https://github.com/DrVelvetFog/verified-examples/actions/runs/34346864122): same | yes, exit 1, read-only |

Each install is one file, sixteen lines, no inputs:

```yaml
name: attest
on:
  push:
    branches: [main]
  pull_request:
permissions:
  contents: read
  id-token: write
  pull-requests: read
jobs:
  attest:
    runs-on: ubuntu-latest
    steps:
      - uses: DrVelvetFog/source-review-coverage@v1
```

The offline recompute was `ceb.py --repo <clone> verify-artifact <downloaded artifact>
--signer-repo DrVelvetFog/<name>` on a Mac, against a local clone, with the verifier from
[#22](https://github.com/DrVelvetFog/source-review-coverage/pull/22). It produced the same
seven results the runner did, signed by the workflow identity of the repository in
question, and left the clone's object store untouched.

## What held

- **First run green with no configuration** on all three. The action's own full-history
  checkout was enough; nothing had to be added to any repository.
- **Push-to-`main` found the pull request behind the merge commit** without a `(#N)` in
  the subject: merge commits carry the number in their message, and the discovery reads
  it from the API. A direct push (reversible) was reported as exactly that: *no merged
  pull request is associated with this commit*, record carries no approvals.
- **The merge-commit path is the stronger one.** Both PR-installed repositories merged
  with a merge commit, so replay took its inputs from the commit's two parents rather than
  from the record. The recorded squash inputs were only needed on the direct push.
- **Every signature bound to the right identity.** Each bundle verifies only against
  `--signer-repo` naming the repository whose workflow signed it.

## What a solo repository cannot show

GitHub does not let an author approve their own pull request, so none of these three can
produce a `VERIFIED` verdict, ever, however carefully they are run. That is not a defect
in the action; it is the rule R3 binding doing its job. It does mean the first live
`VERIFIED` on any repository needs a second account, which is why
[#22](https://github.com/DrVelvetFog/source-review-coverage/pull/22) is held for an outside
review and why the fifty-repository test (CE-014) is the real one.

## Friction found

- **Node 20 deprecation warnings** on every run. The action pins `actions/checkout@v4` and
  `actions/upload-artifact@v4`, both of which declare Node 20; the runner now forces them
  onto Node 24 and says so. Harmless today, noisy on every consumer's run, and the
  forcing will not last. Fix: pin the majors that declare Node 24. Filed as CE-018.
- **Two workflow shapes are in circulation.** The three repositories use the sixteen-line
  file above (`pull-requests: read`, no `pull_request_review` trigger).
  [docs/action.md](action.md) shows the fuller one, which re-runs when a review lands and
  can post the residual comment. On the short shape an approval submitted after the last
  push is not attested until the next push, and a residual is only in the artifact. Both
  are correct; the documented shape is the one to recommend, and the three repositories
  will move to it when they are next touched.
- **`object format WARN` on every run**, because every repository is SHA-1. Expected,
  documented in the specification, and nothing a consumer can do short of a SHA-256
  repository. Kept as a warning, not silenced.

A pass establishes review coverage and nothing else: not correctness, not that a human
read anything, not truthful authorship, not reviewer independence, not existence at a
time, not compliance.
