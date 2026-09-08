# Changelog

All notable changes to this repository. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow semver. The
`v1` tag floats to the latest `0.x` release of the action. The predicate's own version
lives in its type URI and changes on its own clock.

## [Unreleased]

### Added

- Intake: issue templates (task, bug, specification question) that produce the backlog
  block unchanged, a pull-request template, `.github/labels.yml` with the labels the
  tracker uses, and `CONTRIBUTING.md` with the integration pull-request pattern, the
  commit-authorship rule and how to run everything locally. (#8)
- The release train: `docs/RELEASING.md` (the fortnight checklist), `tools/release_check.sh`
  (the action description within the Marketplace's 125 characters, branding, `VERSION`
  against the changelog and the tag, examples attested against the version, clean tree;
  runs on every push as an attested example) and `.github/workflows/release.yml`, which
  runs the action at the tag on every published release and attaches the tag's own
  attestation to the release page. (#7)
- The Agent Audit: `audit/TEMPLATE.md` (coverage findings, residual inventory,
  agent-action journal, example drift, findings each with an evidence tier, what the
  audit does not establish), `audit/run.sh` that generates the first two sections from
  a clone, and the scanners it runs, `tools/scan.py` and `tools/scan_squash.py`, now in
  the repository with `--json`. `audit/samples/openmed-2026-07-28.md` reproduces the
  specification's Appendix A on the same clone: 400 merges, 336 identity, 64 residual,
  none with a clean replay. `docs/audit.md`. (#10)
- `experiments/octopus_probe.sh` and `experiments/octopus_probe.md`: a random
  N-parent merge generator that compares Git's native octopus strategy with the
  verifier's left fold, and the answer: not equivalent when two parents rename one path
  differently, because octopus does no rename detection and `merge-tree` does. Folding
  with `-X no-renames` closes the gap on every trial; the verifier change is CE-019. By
  @kshivam4781. (#12, #24)
### Added

- The residual as a pull-request comment: when bytes shipped that no approval covers, the
  action posts one comment with the verdict, each approval and the revision it was given
  on, and the residual as a diff, truncated at a fixed size with a link to the artifact.
  The same comment is edited on re-runs, found by a hidden marker. Silent on clean
  replays unless `comment: always`; `comment: never` to disable. Needs
  `pull-requests: write`; without it the comment is rendered into the artifact and a
  warning says why. `tools/render_comment.py`, `tests/comment/`. (#3)
- `docs/field-notes.md`: what happened on the first three repositories that are not this
  one, what held, what a solo repository cannot show, and the friction found. (#6)
- `docs/signing.md`: how the attestation is signed (the workflow's own OIDC identity,
  rule R4) and why the envelope is detached rather than DSSE — sigstore-python rejects
  the git digest types the in-toto framework defines; an opt-in is proposed upstream as
  sigstore/sigstore-python#1899, and the verifier's DSSE-first fallback reverts by
  itself if it is accepted. (#13)
- `.github/FUNDING.yml` and one README line: the project is sponsorable at
  [github.com/sponsors/DrVelvetFog](https://github.com/sponsors/DrVelvetFog), with an
  organisation tier that buys priority on issues. (#9)
- The verdict as a check run: `check: residual` (or `always`, what a required check
  needs) creates a check run whose inline annotations carry the residual hunks, placed
  on the shipped tree's line numbers. The conclusion follows `fail-on` — `failure` when
  the run is failing, `success` only for `VERIFIED`, `neutral` otherwise, so branch
  protection passes without painting `UNVERIFIED` green. Needs `checks: write`.
  `tools/render_check.py`, `tests/check/`. (#11)

### Fixed

- `replay_merge()` folds a merge of three or more parents with `-X no-renames`, matching
  Git's native octopus strategy, which does no rename detection. Before this, a clean
  octopus merge whose parents rename one path two different ways replayed as a false
  residual (found in #24). Two-parent merges keep rename detection, because that is what
  the forges' merge does. The fold's strategy is now recorded in
  `mergeTransform.strategy` (`ort` or `ort -X no-renames`), the probe's default fold
  matches the verifier again, and `tests/replay/` holds a rename/rename(1:2) octopus
  fixture that must replay to the identical tree. (#31)

### Changed

- The actions this action pins, `actions/checkout` and `actions/upload-artifact`, moved
  from `v4` (Node 20, now deprecated on the runner) to `v7` (Node 24). No functional
  change; every consumer's run stops printing the deprecation warning. Self-hosted
  runners need 2.327.1 or newer. (#26)
- `ceb.py verify-artifact <dir>`: one command for a consumer holding a downloaded artifact
  and a clone. Recomputes the record's claims, checks the signature and binds it to a
  workflow identity, and checks the statement is exactly what the record produces. Exit
  `0` verified, `1` unverified, `2` incomplete, `3` malformed. Read-only by default: the
  replay runs in a throwaway clone that borrows the repository's objects. (#4)
- `verify` gains a statement-binding step. (#4)
- `tests/verify/test_verify_artifact.sh` with a real workflow-signed fixture. (#4)

## [0.2.1] - 2026-09-08

### Changed

- `action.yml` description shortened to the 125 characters the GitHub Marketplace allows. No functional change.

## [0.2.0] - 2026-09-08

The first release of the GitHub Action.

### Added

- `action.yml`: a composite action that records, signs and verifies a source-review-coverage
  attestation for every revision that lands, in one line. Checks the repository out with
  full history itself. Inputs `mode`, `fail-on`, `sign`, `upload`, `checkout`,
  `declared-by`, `sigstore-version`, `artifact-name`, `approvals`; outputs `verdict`,
  `signatures`, `residual`, `record`, `statement`, `bundle`, `pr`, `approvals`. (#1, #18)
- Approvals from the forge's review data, each bound to the tree of the revision it was
  given on, read with the workflow's own token. On `pull_request` and
  `pull_request_review` events the pull request's own reviews; on a push to `main` the
  merged pull request is discovered from the commit and `refs/pull/N/head` fetched so
  approved revisions can be replayed. (#2, #19)
- `ceb.py verify`: a merge-transform step that replays whether or not the record carries
  approvals, so bytes produced at merge time are reported even before any review is
  bound; per-approval replay onto the landing base, with stale earlier approvals reported
  as warnings and the residual measured from the most recent approval; `--json` output
  with the same content and exit code as the human report. (#18, #19)
- `ceb.py record --approvals FILE`, with `source` labelling whether a tree was resolved
  from git or reported by the forge; a forge tree that contradicts git is refused. (#19)
- `tests/action/test_approvals.sh`: sixteen offline checks over identity, replay,
  approved-then-pushed, stale approvals, unreachable revisions, true merge commits and
  the bare `--approver` form. (#19)
- `examples/quickstart.sh`, an offline walk-through whose execution is attested with
  `xv`; `CHANGELOG.md`; `VERSION`. (#5)

### Changed

- The dogfood workflow runs the action on push to `main`, on pull requests and on
  submitted reviews. Signing and signature verification run from an isolated venv with a
  pinned `sigstore`, the only package the action installs. (#18)

## [0.1.0] - 2026-07-28

### Added

- The `source-review-coverage` predicate, v0.1: specification, protobuf definition and
  the type URI `https://drvelvetfog.github.io/source-review-coverage/v0.1`, served from
  GitHub Pages.
- `tools/ceb.py`, the reference verifier: `record`, `verify`, `intoto`. Replay via
  `git merge-tree --write-tree`, squash recovery via pull references, multi-parent replay
  from the object graph, residual diff on mismatch.
- Keyless Sigstore signing by workflow identity in `.github/workflows/attest.yml`.

[Unreleased]: https://github.com/DrVelvetFog/source-review-coverage/compare/v0.2.1...HEAD
[0.2.1]: https://github.com/DrVelvetFog/source-review-coverage/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/DrVelvetFog/source-review-coverage/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/DrVelvetFog/source-review-coverage/releases/tag/v0.1.0
