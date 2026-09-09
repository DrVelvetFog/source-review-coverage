# Contributing

This repository is a GitHub Action, a verifier, and a predicate specification, all
serving one claim: the code that shipped is the code a human approved, and a stranger can
recompute that with git alone. The plan is
[PLANS/V1/HORIZON_BRIEF.md](PLANS/V1/HORIZON_BRIEF.md); the backlog it generates is
[PLANS/V1/EXECUTION/tasks.md](PLANS/V1/EXECUTION/tasks.md), one task per issue.

## Where to start

Issues labelled `help wanted` are open to anyone; `good first issue` needs no prior
knowledge of the specification. Comment on the issue to claim it and it is assigned
within a day. If the specification is unclear, file a *Specification question* rather
than guessing; if the action misbehaves, a *Bug*. New work goes in as a *Task* using the
template unchanged, so the tracker can read it.

## Running things locally

Python 3 and git 2.38 or newer. The verifier and the tests are stdlib only; nothing to
install.

```bash
bash tests/action/test_approvals.sh          # approvals bound to revisions, 8 scenarios
bash tests/comment/test_render_comment.sh    # the pull-request comment, 14 cases
bash examples/quickstart.sh                  # approved-then-pushed, end to end, offline
```

Every example in the README and the docs is executed in CI and attested; `xv check
--rerun --strict` (from [verified-examples](https://github.com/DrVelvetFog/verified-examples))
runs the same check here. The action's own logic runs outside a runner with
`SRC_SIGN=false bash action/attest.sh`; signing needs a virtual environment with
`sigstore==4.5.0` and is exercised by CI, not locally.

## How a change lands

Open a pull request from a fork as usual. Review happens there.

The last mile is different from most repositories, for a reason that is the point of
the project. The attestation on `main` must be signed by *this repository's* workflow
identity (rule R4), and a pull request from a fork cannot obtain that identity, so the
commit that lands is always pushed from here. To keep your authorship intact through
that, a maintainer opens an **integration pull request**: a branch in this repository
carrying your commits unchanged (same author, same message; `cherry-pick` preserves
both), with any integration commits (wiring, tests, changelog) on top, labelled
`integration`. Its description names your pull request with `Closes #n`, so yours closes
when it merges. Your commits are then in `main` under your name, the changelog entry
credits you, and the release notes thank you by handle.

What that means in practice: keep your pull request's commits clean enough to carry over
as they are. Force-pushing to your branch during review is fine; the integration branch
is cut when review is done.

## Commits

Commits carry the name of the person accountable for them and nothing else. No tool or
vendor attribution: no `Co-Authored-By:` naming an assistant, no "generated with"
trailer. A commit is a claim about who stands behind a change, and a tool does not stand
behind anything. AI assistance is welcome, and saying so in the pull request description
is the right place for it; the disclosure belongs to the pull request, the authorship to
the commit. A sign-off is not required.

## Labels

Maintainers apply labels. `roadmap-v1` marks backlog tasks; `P0`–`P2` is priority;
`spec` is for the predicate; `integration` marks a maintainer pull request carrying
someone else's work. The full list with colours is [.github/labels.yml](.github/labels.yml).
To recreate them on a fresh repository:

```bash
python3 -c '
import re, shlex
for n, c, d in re.findall(r"- name: \"?([^\"\n]+?)\"?\n  color: \"?([0-9a-f]{6})\"?\n  description: (.*)", open(".github/labels.yml").read()):
    print("gh label create", shlex.quote(n), "--color", c, "--description", shlex.quote(d), "--force")
' | sh
```

## Releases

A release every fourteen days from v0.2.0, whether or not it is exciting;
[CHANGELOG.md](CHANGELOG.md) keeps an `[Unreleased]` section that each pull request adds
to. Contributors are thanked by name in the entry and on the release page.

A pass establishes review coverage and nothing else: not correctness, not that a human
read anything, not truthful authorship, not reviewer independence, not existence at a
time, not compliance.
