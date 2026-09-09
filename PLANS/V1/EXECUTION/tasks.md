# V1 execution backlog

Generated from `PLANS/V1/HORIZON_BRIEF.md` (2026-09-08). One task becomes one issue. The
issue body is the block below verbatim; the trailer line carries the fields the tracker
uses. IDs are stable; never reuse one. Sizes: S ≤ half a day, M ≤ 2 days, L ≤ a week.

Labels: `roadmap-v1`, plus `P0` / `P1` / `P2`, plus `help wanted` and
`good first issue` where marked.

---

## CE-001 — Composite GitHub Action that records and signs one merge

**Summary.** The one-line artifact. A composite action at the repository root that, on a
push to a protected branch, builds the record, emits the in-toto statement, signs it with
the workflow identity, verifies the signature, and uploads the three files as an artifact.

**Scope.**
- `action.yml` (composite) wrapping `tools/ceb.py record | intoto` + `sigstore sign` +
  `ceb.py verify --bundle --signer-repo`.
- Inputs: `mode` (`push` | `pull_request`), `fail-on` (`never` | `signature` |
  `residual`), `sign` (bool, default true), `upload` (bool, default true).
- Outputs: `verdict`, `residual` (path or empty), `statement`, `bundle`.

**Acceptance criteria.**
- `uses: DrVelvetFog/source-review-coverage@v1` in a fresh repository produces a signed
  attestation on the first push to `main` with no other configuration.
- `fail-on: signature` fails the job when the bundle does not verify; `never` only annotates.
- The action runs with stdlib Python on `ubuntu-latest`; `sigstore` is the only pip install.
- `attest.yml` in this repository is rewritten to use the action (dogfood).

**Out of scope.** PR review data (CE-002), PR comments (CE-003), Marketplace listing (CE-005).

**Files.** `action.yml`, `.github/workflows/attest.yml`, `docs/action.md`.

Task: CE-001 · Milestone: v0.2 · Priority: P0 · Size: M · Depends on: — · Brief: §4.1, §5

---

## CE-002 — Source approvals from the forge's review data

**Summary.** Today the workflow passes no `--approver`, so every verdict is `UNVERIFIED`.
In `pull_request` mode the action reads the PR's reviews through the workflow token and
records each approval bound to the tree hash it was given on (rule R3).

**Scope.**
- Query `GET /repos/{o}/{r}/pulls/{n}/reviews` with `GITHUB_TOKEN`; keep `APPROVED`
  reviews; resolve each review's `commit_id` to its tree; pass as `--approver` with hash.
- Record the reviewed head as the PR head at the time of the last approval, not `HEAD`.
- Never accept a personal access token; the workflow token's `pull-requests: read` is enough.

**Acceptance criteria.**
- A PR approved then merged without further pushes yields `VERIFIED (identity)` or
  `VERIFIED (replay)`.
- A PR approved, then pushed to, then merged yields `UNVERIFIED (residual)` naming the
  post-approval bytes.
- Fixture workflow under `tests/action/` reproduces both on a throwaway repository.

**Out of scope.** Non-GitHub forges. Reviewer independence (spec §6).

**Files.** `action.yml`, `tools/ceb.py` (approver hash form), `tests/action/*`, `docs/action.md`.

Task: CE-002 · Milestone: v0.2 · Priority: P0 · Size: M · Depends on: CE-001 · Brief: §5, §9.4

---

## CE-003 — Render the residual as a pull-request comment

**Summary.** The failure case is the product. When replay leaves a residual, post one
comment on the PR with the residual diff, which approvals covered which tree, and the
one-paragraph explanation of what a residual is. Update the same comment on re-runs.

**Scope.**
- Comment body: verdict line, table of approvals (reviewer, tree, time), residual as a
  fenced diff truncated at a fixed size with a link to the artifact.
- Idempotent: find the previous comment by a hidden marker and edit it.
- Silent on identity and clean replay unless `comment: always`.

**Acceptance criteria.**
- Conflict-resolution residual on a squash merge renders the exact hunk, verified against
  the `experiments/end_to_end.sh` case C.
- No comment is posted on a clean replay by default.
- Comment text carries the spec §6 line: what a pass does not establish.

**Out of scope.** Check-run annotations (CE-011).

**Files.** `action.yml`, `tools/render_comment.py`, `docs/action.md`.

Task: CE-003 · Milestone: v0.2 · Priority: P1 · Size: M · Depends on: CE-002 · Brief: §4.1, §9.5

---

## CE-004 — Verify subcommand for consumers: one command, offline

**Summary.** A consumer who downloads the artifact needs one command that recomputes
everything the record claims, with the repository as the only input besides the files.

**Scope.**
- `ceb.py verify-artifact <dir> --repo <path> [--signer-repo]` = signature + coverage
  replay + statement/record binding in one call.
- Exit codes: 0 verified, 1 residual, 2 incomplete (signatures unchecked), 3 malformed.
- Read-only: replay works on a copy or with `--allow-write` explicit.

**Acceptance criteria.**
- The three CI-signed examples from CE-001 verify on a second machine with no network.
- Tampering with any of the three files produces a distinct, named failure.
- `docs/verify.md` walks a stranger through it in under ten lines.

**Out of scope.** Transparency-log lookups.

**Files.** `tools/ceb.py`, `docs/verify.md`, `tests/verify/*`.

Task: CE-004 · Milestone: v0.2 · Priority: P1 · Size: M · Depends on: CE-001 · Brief: §3

---

## CE-005 — Marketplace listing and the "one line" README

**Summary.** The README leads with the one line, the first-merge screenshot and the §6
disclaimer. The action is published to GitHub Marketplace with branding and a `v1` tag.

**Scope.**
- README rewrite: one line to add, what you get on the first merge, what a pass does not
  establish, links to spec and verify docs.
- `branding` block in `action.yml`; `v1` floating tag; `v0.2.0` release.

**Acceptance criteria.**
- Marketplace page live; `uses: DrVelvetFog/source-review-coverage@v1` resolves.
- README verified with `xv`: every example in it carries an execution attestation.

**Out of scope.** Paid App listing.

**Files.** `README.md`, `action.yml`, `examples/manifest.json`, `CHANGELOG.md`.

Task: CE-005 · Milestone: v0.2 · Priority: P0 · Size: S · Depends on: CE-001, CE-004 · Brief: §4.1, §4.5

---

## CE-006 — Dogfood on three external repositories

**Summary.** The action running on three repositories that are not this one, chosen from
Tony's own public repositories first, before asking anyone else.

**Scope.**
- Install on `reversible`, `evidence-tier`, `verified-examples` via PR.
- Collect the first-merge attestation from each; record findings in `docs/field-notes.md`.

**Acceptance criteria.**
- Three repositories show a green attest run and an uploaded artifact.
- Any friction found becomes a CE task before v0.2.0 ships.

**Out of scope.** Third-party repositories (CE-014).

**Files.** `docs/field-notes.md`.

Task: CE-006 · Milestone: v0.2 · Priority: P1 · Size: S · Depends on: CE-005 · Brief: §5

---

## CE-007 — Release train: CHANGELOG, tags, fortnight cadence

**Summary.** Keep-a-Changelog file, semver tags, a release checklist, and a calendar
commitment: a release every fourteen days from v0.2.0 whether or not it is exciting.

**Scope.**
- `CHANGELOG.md` with `[Unreleased]`; `docs/RELEASING.md` checklist; release notes thank
  every contributor by name.
- Release workflow builds the artifact-signed attestation for the tag itself.

**Acceptance criteria.**
- v0.2.0 and v0.3.0 ship on schedule with changelogs.
- Each release page lists contributors by handle.

**Files.** `CHANGELOG.md`, `docs/RELEASING.md`, `.github/workflows/release.yml`.

Task: CE-007 · Milestone: v0.3 · Priority: P0 · Size: S · Depends on: CE-005 · Brief: §4.2

---

## CE-008 — Issue templates, labels and CONTRIBUTING

**Summary.** The factory's intake surface. Templates that produce the task-block format
above, labels created, CONTRIBUTING with the integration-PR pattern and the no-vendor-
attribution rule for commits.

**Scope.**
- Templates: task, bug, spec question. Labels: `roadmap-v1`, `P0`–`P2`, `help wanted`,
  `good first issue`, `spec`.
- CONTRIBUTING: how a PR lands (maintainer integration PR preserving authorship), test
  commands, what gets a `help wanted` label.

**Acceptance criteria.**
- Filing the CE-0xx backlog uses the template unchanged.
- Labels exist; first three `good first issue` items are tagged.

**Files.** `.github/ISSUE_TEMPLATE/*`, `CONTRIBUTING.md`, `.github/labels.yml`.

Task: CE-008 · Milestone: v0.3 · Priority: P1 · Size: S · Depends on: — · Brief: §4.2, §4.3

---

## CE-009 — GitHub Sponsors with an organisation tier

**Summary.** Sponsors enabled on the account with a `FUNDING.yml` in the repository and
tiers: individual, and an organisation tier that buys priority on `help wanted` issues.

**Acceptance criteria.**
- Sponsor button visible on the repository; tiers published; README links it once.

**Files.** `.github/FUNDING.yml`, `README.md`.

Task: CE-009 · Milestone: v0.3 · Priority: P2 · Size: S · Depends on: — · Brief: §6 L3

---

## CE-010 — Agent Audit: the report template the verifier fills in

**Summary.** The consulting bridge. A report template whose every finding carries an
evidence tier (`ev`) and whose review-coverage section is generated by running the
verifier over the client's merge history. Sold as a one-week engagement; the same
template, self-serve, is the Gumroad kit.

**Scope.**
- `audit/TEMPLATE.md` with sections: coverage findings, residual inventory, agent-action
  journal (`rv`), example drift (`xv`), what this audit does not establish.
- `audit/run.sh` that produces the coverage and residual sections from a clone.

**Acceptance criteria.**
- Running `audit/run.sh` on `maziyarpanahi/openmed`'s public history reproduces the
  Appendix A numbers (336 identity, 64 residual on the sampled 400).
- Template published; UIG Studios "Agent Audit" offer links the sample report.

**Out of scope.** Pricing pages (site repository). Client work itself.

**Files.** `audit/TEMPLATE.md`, `audit/run.sh`, `docs/audit.md`.

Task: CE-010 · Milestone: v0.3 · Priority: P1 · Size: M · Depends on: CE-004 · Brief: §6 L1–L2

---

## CE-011 — Check-run annotations instead of only comments

**Summary.** Surface the verdict as a check run with inline annotations on the residual
lines, so it shows in the Files tab and can be a required check.

**Acceptance criteria.** Residual lines annotated; check conclusion follows `fail-on`.

**Files.** `action.yml`, `tools/render_check.py`.

Task: CE-011 · Milestone: v0.3 · Priority: P2 · Size: M · Depends on: CE-003 · Brief: §5 · `help wanted`

---

## CE-012 — Octopus replay equivalence probe

**Summary.** Spec §5c states the left fold of two-way merges is not proven equivalent to
Git's native octopus strategy. Build the probe that searches for a counterexample and
document the result either way.

**Acceptance criteria.** A script under `experiments/` that generates random N-parent
merges and compares; a written result in the spec changelog.

**Files.** `experiments/octopus_probe.sh`, `v0.1/index.md` (changelog).

Task: CE-012 · Milestone: v0.3 · Priority: P2 · Size: M · Depends on: — · Brief: §2 · `help wanted` `good first issue`

---

## CE-013 — sigstore-python digest typing: upstream conversation

**Summary.** The DSSE typing fallback exists because sigstore-python rejects
`gitCommit`/`gitTree` digests the in-toto framework defines. Open the upstream issue with
the reproduction, citing the framework spec and #1018's rationale, proposing an opt-in
rather than a widening of the default set.

**Acceptance criteria.** Issue filed with a minimal repro; the verifier's fallback path
documented as reverting automatically if accepted.

**Files.** `docs/signing.md`.

Task: CE-013 · Milestone: v0.3 · Priority: P2 · Size: S · Depends on: — · Brief: §2, §8

---

## CE-014 — Fifty repositories: the demand test

**Summary.** The v0.4 gate. Track adoption of the action without instrumentation the
action does not have: GitHub's dependents view, Marketplace installs, and attestations
uploaded by public repositories. Publish the number at day 90.

**Scope.**
- `docs/adoption.md` updated each release with the count and the method.
- Ask, once, in the communities where the audience lives (in-toto, SLSA, OpenSSF lists)
  with the one line and the §6 disclaimer; no cold outreach beyond that.

**Acceptance criteria.** A day-90 number and the v0.5 go/no-go recorded in the brief.

**Files.** `docs/adoption.md`, `PLANS/V1/HORIZON_BRIEF.md` (decision record).

Task: CE-014 · Milestone: v0.4 · Priority: P0 · Size: S · Depends on: CE-005 · Brief: §5 v0.4

---

## CE-015 — in-toto/attestation#581: land the predicate

**Summary.** The positioning move. Respond to maintainer review, keep spec/proto/emitter
aligned, and land the predicate in the framework's list.

**Acceptance criteria.** PR merged, or a written maintainer decision recorded in the brief.

**Files.** `v0.1/index.md`, `v0.1/source_review_coverage.proto`.

Task: CE-015 · Milestone: v0.4 · Priority: P1 · Size: S · Depends on: — · Brief: §2, §8

---

## CE-016 — Consolidation decision: rv/ev/xv in or out

**Summary.** Decide, with evidence from CE-006 and CE-010, whether the feeders should be
vendored into this repository, pinned as versions, or left as independent tools. Write
the decision and its reasons; do not consolidate by default.

**Acceptance criteria.** A one-page decision record under `PLANS/V1/DECISIONS/`.

**Files.** `PLANS/V1/DECISIONS/0001-feeders.md`.

Task: CE-016 · Milestone: v0.4 · Priority: P2 · Size: S · Depends on: CE-006, CE-010 · Brief: §7, §9.3

---

## CE-017 — Organisation-wide coverage report (v0.5 design only)

**Summary.** The paid tier's first feature, designed not built: one report across all
repositories in an organisation, retention aligned to EU AI Act Art. 19, from attestations
the free action already produces.

**Acceptance criteria.** A design doc with the data model, the hosting choice inside the
existing accounts, and the billing path via GitHub Marketplace. No code.

**Files.** `PLANS/V1/DESIGN/org-report.md`.

Task: CE-017 · Milestone: v0.5 · Priority: P2 · Size: M · Depends on: CE-014 · Brief: §5 v0.5, §6 L4

---

## CE-018 — Node 24 runtime for the actions this action pins

**Summary.** Found by CE-006. `action.yml` pins `actions/checkout@v4` and
`actions/upload-artifact@v4`, both of which declare Node 20; every run on every consumer
now prints a deprecation warning and the runner forces Node 24. Pin the majors that
declare Node 24 before the forcing stops.

**Scope.**
- `action.yml`: `actions/checkout@v7`, `actions/upload-artifact@v7`.
- The two workflows in this repository: the same pins.
- CHANGELOG entry under Changed.

**Acceptance criteria.**
- A pull-request run and a push-to-`main` run on this repository with no
  `Node.js 20 is deprecated` warning.
- The three CE-006 repositories show the same after the next `v1` re-float.

**Out of scope.** Any behaviour change in the checkout itself (v7 refuses fork checkouts
on `pull_request_target`; this action never runs on that event).

**Files.** `action.yml`, `.github/workflows/attest.yml`,
`.github/workflows/verified-examples.yml`, `CHANGELOG.md`.

Task: CE-018 · Milestone: v0.3 · Priority: P2 · Size: S · Depends on: — · Brief: §4.1
