# Adoption

This file carries the count and the method that produced it, updated on every release, so
the day-90 number is read against a method fixed before the number existed and not chosen
after it.

The decision at day 90 is build the paid GitHub App (v0.5) or keep the Action free and
treat the lane as standing. Day 0 is 2026-09-08, the v0.2.0 release and the Marketplace
listing. **Day 90 falls on 2026-12-07.**

**The gate.** Fifty repositories was the original test (brief §5). It was amended on
2026-09-17, at day 9, with the count at zero and before any day-90 figure existed:
v0.5 needs **one repository that is not mine running the Action, and one inbound
conversation**, and neither half alone. The reasoning is in the brief under §5 v0.4 and
as decision 7; the timing is the point, because a gate amended after its number arrives
is a gate that chose itself. Fifty is still what adoption would look like.

## The count

| Date | Day | Repositories, not mine | Method sources agreeing |
|---|---|---|---|
| 2026-09-17 | 9 | **0** | dependents, code search, workflow-path search |

Four repositories run the Action today — `source-review-coverage`, `verified-examples`,
`evidence-tier` and `reversible` — and all four are mine, so none of them counts. The
field notes say the same thing at more length: a solo repository cannot show that anyone
else wants this.

## Method

Four sources, none of which requires instrumentation the Action does not have. The
Action reports nothing home and will not; that is the constraint this method works
inside, and the reason every figure here is an undercount.

1. **Dependents.** `github.com/DrVelvetFog/source-review-coverage/network/dependents`.
   Counts public repositories GitHub has linked to this one. It is the closest thing to
   an authoritative number and it lags.
2. **Code search.** `"DrVelvetFog/source-review-coverage"` and
   `"source-review-coverage@v1"` through the code search API. Finds workflow files that
   name the Action.
3. **Workflow-path search.** The same string restricted to `path:.github/workflows`.
   Narrower, and it separates a genuine caller from a mention in prose.
4. **Marketplace installs.** Visible to me on the listing's own page and nowhere else.
   Not reproducible by a reader, so it is recorded as a figure I assert and never as one
   the table above rests on.

Run 1 through 3 and record the largest, with the sources that agree. A disagreement
between them is worth a line in the table, because the disagreement is information about
the method.

## What this does not establish

A repository calling the Action is not a repository that reads the result, and neither is
evidence that anyone acted on a residual. The count is a count of callers. It says
nothing about whether the verdict changed a decision, which is the thing the paid tier
would have to be worth, and no method here can see it.

Pull-request counts are not a metric (brief §5). Stars are not on this list either.

## The ask

Scope allows one ask, once, in the communities where the audience lives, carrying the one
line and the disclaimer below. No cold outreach beyond that. Recorded here when made,
with the date and the venue, so the count can be read against it.

| Date | Venue | Link |
|---|---|---|
| 2026-09-17 | `slsa-framework/source-tool`, as an issue | [#450](https://github.com/slsa-framework/source-tool/issues/450) |

The venue is a GitHub issue and not a mailing list because SLSA's `CONTRIBUTING.md` says
the project is authored on GitHub issues, the OpenSSF SLSA list has eleven members and no
topics, and `groups.google.com/g/slsa-discussion` cannot be read without signing in. The
in-toto venue is held until in-toto/attestation#581 has an answer, so that a nudge and an
ask do not arrive in the same week in front of the same people.

The ask is a question about scope before it is anything else: whether revision-level
evidence for `[Final revision approved]` belongs in `source-tool`, whose `REVIEW_ENFORCED`
control establishes that the gate is configured. If it does, contributing there beats
maintaining a parallel thing, and that answer is worth more than a caller.

---

A pass establishes review coverage and nothing else: not correctness, not that a human
read anything, not truthful authorship, not reviewer independence, not existence at a
time, not compliance.
