# Source Review Coverage — V1 Horizon Brief

Status: draft, 2026-09-08. This is the plan the execution backlog is generated from.
Tasks reference sections here by number. The brief is frozen per milestone; changes
land as a new dated revision, not as edits.

## 0. One sentence

Evidence, recomputable by a stranger, that the code which shipped is the code a human
approved — issued as a signed in-toto attestation, one line to add to a repository.

## 1. What this is and who it is for

Coding agents now write a large share of the changes that land on `main`. The question
auditors, security teams and maintainers are starting to ask is not "was this AI-written"
but "what did the agent change, and did a person actually approve *that*". Today the
answer is asserted by the forge that performed the merge, to a consumer who cannot check
it. SLSA v1.2 Source Track L4 already requires two-party review of the final revision and
explicitly leaves the mechanism undefined (§4 of the spec).

The buyer is an engineering organisation under that pressure: SOC 2 CC6.8, HIPAA
164.312(b), EU AI Act Arts. 12 and 19, ISO 42001 assessors. The user is whoever owns the
repository's CI. The artifact is a GitHub Action that adds one line to a workflow and
emits, for every merge, a signed record a third party can recompute offline.

Who it is not for: individuals evaluating agent tools for fun. They are welcome, but they
are not the buyer, and the roadmap does not bend for them.

## 2. What already exists (the starting position)

- The predicate, v0.1: spec, protobuf, type URI resolving at
  `https://drvelvetfog.github.io/source-review-coverage/v0.1`.
- The reference verifier `tools/ceb.py` (stdlib Python + git): `record`, `verify`,
  `intoto`. Replay via `git merge-tree --write-tree`, squash recovery via pull refs,
  multi-parent replay from the object graph, residual diff emitted on mismatch.
- Validation against 810 production merges across three live repositories: every merge
  explained as identity or replay, zero false positives, 64 residuals all explained as
  conflict resolutions (spec Appendix A).
- Keyless Sigstore signing by workflow identity in `.github/workflows/attest.yml`
  (design rule R4 satisfied in production). Bundles verify offline on another machine.
- Upstream standing: `sigstore/sigstore-python#1846` merged 2026-09-08 (the parser now
  preserves the validation error); `in-toto/attestation#581` (this predicate) open,
  awaiting maintainer review.
- Runtime feeders, separate MIT repositories, each with an offline verifier and a spec:
  `rv` (reversible shell actions, journal + per-path undo), `ev` (evidence tiers
  ran/read/told/recalled/inferred as an in-toto predicate), `xv` (verified examples).

Known blocker carried forward: sigstore-python's in-toto `Statement` restricts the
`DigestSet` to SHA-2/SHA-3 and rejects `gitCommit`/`gitTree`, which the in-toto framework
itself defines. Deliberate upstream (their #1018). Statements are therefore signed as
artifacts, not in a typed DSSE envelope; the verifier tries DSSE first and falls back.

## 3. Principles (from the spec's design rules; the plan does not relitigate them)

- R1 content, not names. R3 an approval binds to the reviewed tree hash. R5 recomputed is
  reported separately from asserted. R6a replay is driven by resolved object IDs.
- Never print `VERIFIED` for something that was not recomputed. Signatures unchecked means
  `INCOMPLETE`, said out loud.
- A pass establishes review coverage. It does not establish correctness, that a human read
  anything, truthful authorship, reviewer independence, existence at a time, or
  compliance (spec §6). Marketing copy inherits this list verbatim.
- Quiet on well-run repositories. A check that fires constantly is worthless.
- Stdlib and git only in the verifier. No network in verification. No new hosting.

## 4. The five mechanisms, applied

1. **Artifact before repository.** The GitHub Action is the artifact. It has to be
   adoptable in one line by someone who has never read the spec, and useful on the first
   merge. Everything in milestone v0.2 serves that.
2. **Plan → generated backlog → agent-built PRs → CI gates → release train.** This brief
   generates `EXECUTION/tasks.md`; each task becomes an issue with an ID, milestone,
   priority, size and dependencies. Releases every two weeks with a changelog. Every
   release thanks contributors by name.
3. **Community loop.** `help wanted` and `good first issue` from the first backlog.
   Assign within a day, merge within days. External PRs land via an integration PR that
   preserves the contributor's commit and authorship.
4. **One lane, held.** Trust evidence for agent work. The desktop app, PoR and the x402
   work become reference consumers or feeders; they do not lead.
5. **Distribution where the audience lives.** GitHub Marketplace (Actions), the OpenSSF,
   SLSA, in-toto and sigstore communities. Not model hubs, not agent plugin marketplaces.

## 5. Milestones

### v0.2 — "one line" (days 0–30)

The Action exists, is listed on the Marketplace, and is running on at least three
repositories that are not this one. Approvals come from the forge's review data, so a PR
merge produces a real coverage verdict instead of `UNVERIFIED`. A residual is rendered
as a PR comment showing the exact bytes that shipped with no approval covering them.

### v0.3 — "release train" (days 30–60)

Two releases shipped on the fortnight cadence with changelogs. Issue templates, labels,
CONTRIBUTING and the integration-PR pattern in place. GitHub Sponsors enabled with an
organisation tier. The consulting bridge offer (an Agent Audit delivered by running this
verifier and the feeders over a client's repository and agent transcripts) is live on the
UIG Studios site.

### v0.4 — "measured" (days 60–90)

Fifty repositories using the Action is the demand test. At ninety days the numbers that
matter are: repositories using the Action, attestations issued, sponsors, inbound audit
leads. Pull-request counts are not a metric. The decision at day 90: build the paid
GitHub App (v0.5) or keep the Action free and treat the lane as standing rather than
revenue.

### v0.5 — paid tier (gated on v0.4)

A GitHub App billed per private repository through GitHub Marketplace. Hosted
attestation store, organisation-wide coverage report, retention aligned to EU AI Act
Art. 19. Free for public repositories. Only built if the demand test passes.

## 6. Monetisation ladder (all red-line safe: no custody, no tokens, no PII)

| Rung | What | Channel | When |
|---|---|---|---|
| L0 | Action, verifier, spec, feeders | free, Apache-2.0 / MIT | now |
| L1 | Agent Audit Kit: the audit rubric + report template, self-serve | Gumroad, one-time | v0.3 |
| L2 | Agent Audit (1 week), Integration Sprint, Agent Build | UIG Studios site, inbound only | v0.3 |
| L3 | Sponsors with an org tier (priority issues) | GitHub Sponsors | v0.3 |
| L4 | Paid GitHub App per private repo | GitHub Marketplace billing | v0.5, gated |

Contract and full-time work remain the income floor for the year. This plan makes the
résumé line and the inbound surface; it does not pretend to replace a salary in 2026.

## 7. Non-goals (this horizon)

Detecting AI authorship from source. Scoring code quality. Runtime agent monitoring.
Replacing code review. Producing a compliance certificate. Supporting forges other than
GitHub before v0.5. Consolidating rv/ev/xv into this repository before there is a reason
(a decision task exists; the default is pinned versions).

## 8. Risks and what we do about them

- **Incumbents**: GitHub artifact attestations, Chainguard, "SLSA for AI" efforts. We are
  the predicate and verifier layer for a requirement SLSA published and left undefined;
  compose with all of them, compete with none. The in-toto PR is the positioning move.
- **Silence**: fifty repositories may not come. That is what the demand test is for; the
  answer at day 90 is honest either way.
- **Squash-heavy world**: most repositories squash, so the commercially relevant check is
  the conflict-resolution residual, not the evil merge. The Action leads with it.
- **Sigstore digest typing**: carried as an upstream conversation, not a blocker.
- **Identifier lock-in**: the type URI is bound to the `DrVelvetFog` username. Renaming
  the account breaks every attestation ever issued. Do not rename the account.

## 9. Decisions this brief makes (ratify or overturn before the backlog is filed)

1. The flagship repository is `DrVelvetFog/source-review-coverage`. The name stays; the
   `change-evidence` working name retires.
2. The Action lives in this repository at the root (`uses: DrVelvetFog/source-review-coverage@v1`).
3. rv, ev and xv stay separate MIT repositories, pinned by version, until a consolidation
   task proves a reason.
4. Approvals are sourced from GitHub review data via the workflow token; the Action never
   asks for a personal token.
5. Residuals are rendered as diffs in a PR comment, never as a boolean status alone.
6. Release cadence is fourteen days, starting with v0.2.0.
