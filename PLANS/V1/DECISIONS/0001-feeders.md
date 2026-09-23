# 0001 — rv, ev and xv stay separate repositories

Status: Accepted, 2026-09-23 (CE-016). Ratifies brief decision 3.

## Context

Three runtime feeders sit beside this project, each its own MIT repository with an
offline verifier and a spec:

- `rv` ([reversible](https://github.com/DrVelvetFog/reversible)) — reversible shell
  actions, a journal plus per-path undo.
- `ev` ([evidence-tier](https://github.com/DrVelvetFog/evidence-tier)) — evidence tiers
  (ran / read / told / recalled / inferred) as an in-toto predicate.
- `xv` ([verified-examples](https://github.com/DrVelvetFog/verified-examples)) — verified
  examples; this repository calls it at release time to attest its own examples.

The question CE-016 asks is whether to vendor them into this repository, pin them as
versions, or leave them independent. The brief's non-goals already say not to consolidate
"before there is a reason"; this record fixes that as a decision with a named trigger that
would reverse it, so the default is chosen on purpose rather than by drift.

Two closed tasks are the evidence. CE-006 installed this Action on all three feeder
repositories: each ran green on the first try with the sixteen-line workflow and no
configuration, and each first-merge artifact recomputed offline on another machine
(`docs/field-notes.md`). CE-010 fixed the report the verifier fills in. Neither found a
place where a feeder had to live inside this repository to do its job.

## Decision

Keep `rv`, `ev` and `xv` as separate MIT repositories. Where this repository depends on
one — today only `xv`, at release time — reference it by a tagged version, not a floating
branch. Do not vendor their source into this tree.

## Why not vendor, why not float

- **The Action a consumer runs depends on none of them.** `uses:
  DrVelvetFog/source-review-coverage@v1` pulls no feeder. `xv` is a tool this project uses
  to attest its own examples; `ev` is a predicate that composes with the verifier's
  output; `rv` is adjacent. Vendoring would add code to the Action that no consumer runs.
- **Independent verifiability is the point.** Each feeder ships its own offline verifier
  and spec, provable from its own clone. Folding them in couples their release cadences to
  this one and makes each harder to check on its own, which is the opposite of what they
  are for.
- **The dogfood ran them as separate installs, and that was worth more.** The three
  feeder repositories are also this Action's first three reference consumers. As separate
  installs they are evidence the Action works across repositories; vendored, they would be
  the same repository testing itself.
- **Fewer identifiers to lock in.** The predicate type URI is already bound to the
  `DrVelvetFog` account (brief risk, section 8). Entangling three more repositories'
  identities into this one widens that exposure for no gain.
- **Floating is rejected for a different reason.** A release must be reproducible, so a
  feeder this repository invokes is pinned to a tag, never tracked from `main`.

## What would reverse this

Reconsider vendoring, as a new decision record, if any of these becomes true:

1. A **consumer** of the Action (not this repository's own release process) needs a feeder
   at runtime.
2. Version drift between a feeder and this repository breaks `release_check` more than
   once across the fourteen-day cadence.
3. An outside adopter asks for the feeders bundled rather than pinned.

None holds today.

## Consequences

- `docs/RELEASING.md` keeps invoking `xv` from its own checkout; the tag it is pinned to
  is recorded where the release process names it.
- New feeders follow the same rule: separate MIT repository, pinned by version, until a
  trigger above proves a reason.
- CE-016 closes with this record. The reversal triggers are the standing test; they are
  not revisited on a schedule, only when one fires.
