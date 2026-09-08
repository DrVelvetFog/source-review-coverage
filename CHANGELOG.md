# Changelog

All notable changes to this repository. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow semver. The
`v1` tag floats to the latest `0.x` release of the action. The predicate's own version
lives in its type URI and changes on its own clock.

## [Unreleased]

### Added

- The residual as a pull-request comment: when bytes shipped that no approval covers, the
  action posts one comment with the verdict, each approval and the revision it was given
  on, and the residual as a diff, truncated at a fixed size with a link to the artifact.
  The same comment is edited on re-runs, found by a hidden marker. Silent on clean
  replays unless `comment: always`; `comment: never` to disable. Needs
  `pull-requests: write`; without it the comment is rendered into the artifact and a
  warning says why. `tools/render_comment.py`, `tests/comment/`. (#3)

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
