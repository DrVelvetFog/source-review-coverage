# Organisation-wide coverage report (design)

Status: Design accepted for v0.5, 2026-10-22 (CE-017). No code in this horizon; the
build is gated on the CE-014 demand test (day 90, 2026-12-07), per brief §5.

## What it is

One page per organisation answering one question for every repository at once: which
revisions on the default branch carry a green source-review-coverage attestation, which
carry a residual, and which carry nothing. The free Action already produces everything
the report reads; this design adds a place where those attestations accumulate and a
report over them. The Action itself does not change — a repository on `@v1` today feeds
the report with no new configuration.

Two principles fix the shape of everything below:

1. **The report asserts nothing the attestations don't prove.** The hosted store is a
   convenience cache over signed artifacts, not an authority. Every number on the page
   is recomputable offline from the attestation files by the verifier this repository
   already ships, and the report links the files it was computed from.
2. **Verify on ingest, fail closed.** Nothing is indexed that the verifier did not
   recompute first. A file that does not verify is retained (it is evidence of
   something) but surfaces as `unverified`, never folded into coverage numbers.

## What the report shows

- Per organisation: repositories enrolled, coverage over the chosen window (default-branch
  revisions with a passing attestation ÷ revisions observed), residual events, uncovered
  revisions, days of retained history.
- Per repository: the same, plus the revision list — each row linking the statement, the
  Sigstore bundle and the verifier result it came from.
- Per revision: verdict (`covered` / `residual` / `no-approvals` / `unverified`), the
  approvals and the trees they bound, the workflow identity that signed, and the Action
  version that produced it.
- Export: the whole report as JSON, plus the content-addressed files underneath it, so a
  consumer can hand the export to the offline verifier and get the same numbers. A report
  that can only be read on our page would be the kind of claim this project exists to
  replace.

## Data model

Content-addressed storage plus one derived index. The files are the truth; rows are a
cache of parsing them.

**`artifact`** — the raw files, keyed by sha256: `record.json`, `statement.json`,
`statement.sigstore.json`, `verify.json`. Stored as received, verified at ingest,
immutable. `residual.diff` is **digest-only by default**: the diff names source bytes,
and for a private repository those bytes do not belong in our store. The row records the
digest and the size; the bytes stay in the repository's own artifact retention unless the
installation explicitly opts in to escrow.

**`attestation`** (index row, derived from the files, unique on `repository + revision +
statement_digest`):

| field | from |
|---|---|
| installation, organisation, repository (forge id + name at ingest) | webhook |
| revision (commit), shipped tree, base tree | `record.json` |
| event (`pull_request` / `push`), pull request number | `record.json` |
| verdict: `covered` / `residual` / `no-approvals` / `unverified` | `verify.json`, recomputed |
| approvals: reviewer login + the tree each approval bound | `record.json` |
| residual digest + size, when present | `record.json` |
| signing identity (workflow ref, repository, run) | Sigstore bundle, recomputed |
| action version | `statement.json` |
| `received_at`, `verified_at` (our clocks, labelled as ours) | ingest |

**`repository`** — forge id, names over time (renames keep history under the id),
enrolment state, retention window.

Names are display data; forge ids are identity. A repository rename must not fork its
history, and a deleted repository keeps its rows for the retention window.

## Ingestion and verification

A GitHub App, installed on the organisation, subscribing to `workflow_run` completions.
On each completed run it looks for the `source-review-coverage-attestation` artifact,
downloads it with the installation token, runs the **existing offline verifier** over the
files, recomputes the Sigstore bundle's binding (this workflow, this repository), and
only then writes rows. Revisions the App never saw (runs before installation, deleted
artifacts) show as gaps, labelled as gaps — backfill walks old workflow runs on request,
subject to the forge's own 90-day artifact retention.

The App asks for the minimum: `metadata`, `actions: read` (artifacts), and nothing that
can write to a repository. It never holds a personal token and never clones source. The
one write surface is its own store.

## Hosting (inside the existing accounts)

The standing two-hub rule: Netlify serves frontends, Render runs backends. Both accounts
exist; nothing new is opened.

- **Render**: the App's webhook receiver and API as one service, and a managed Postgres
  beside it. The artifact files are small JSON (kilobytes); they live in Postgres as
  content-addressed rows — no object store, no third bucket to govern. Scale moves
  (partitioning, an object store) wait for a scale that justifies them.
- **Netlify**: the report frontend, static, reading the API with the viewer's session.
- Secrets: the App's private key and webhook secret live in Render's environment, never
  in the repository.

## Billing (GitHub Marketplace)

The L4 rung as the brief states it: **free for public repositories, billed per private
repository, monthly, through GitHub Marketplace** — the App's plan uses Marketplace
per-unit pricing with the unit "private repository enrolled". Marketplace handles the
money; we never see a card number (no custody, no PII — the red lines hold). Publisher
verification and the Marketplace app review are prerequisites and belong to the build,
not this design. If Marketplace's listing requirements stall the build, the fallback is
the App free during a pilot with billing deferred — not a parallel payment rail.

Public repositories stay free end to end: the Action is free, ingest is free, and an
all-public organisation pays nothing. The paid thing is the hosted aggregate over
private repositories, which is also the only part a public-repo user can't get from raw
artifacts today.

## Retention

Aligned to EU AI Act Article 19's floor for automatically generated logs: attestations
are retained **at least six months**, default **two years**, configurable upward per
installation. Deletion at window end is a recorded event (what was deleted, by digest —
the digests outlive the bytes). Alignment is a retention property, not a legal
conclusion: the report does not make a repository, or anyone, Article-19 compliant, and
the page must not say otherwise.

## What this is not

The non-goals hold. The report does not score code quality, detect authorship, certify
compliance, or replace review. A green page establishes coverage over the window shown,
computed from the attestations listed, and nothing else. The closing line applies to the
report page itself, verbatim.

## Open questions, pre-registered

- **Residual escrow**: is digest-only residual enough for an auditor, or does Art. 12/19
  alignment want the bytes held? Decide with the first real audit conversation, not
  before.
- **Backfill depth**: artifacts expire on the forge after 90 days; is re-running the
  Action over old revisions (recomputing history) in scope for v0.5 or a later rung?
- **Reversal trigger for Postgres-only storage**: the first installation whose artifact
  volume makes Postgres rows the wrong container moves files to object storage; the
  content-addressing makes that move invisible to the data model.

> A pass establishes review coverage and nothing else: not correctness, not that a human
> read anything, not truthful authorship, not reviewer independence, not existence at a
> time, not compliance.
