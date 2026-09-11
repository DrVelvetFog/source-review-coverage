# Octopus replay: is the left fold equivalent to Git's own strategy?

The probe and its answer, from CE-012 ([#12](https://github.com/DrVelvetFog/source-review-coverage/issues/12)),
contributed by [@kshivam4781](https://github.com/kshivam4781) in
[#24](https://github.com/DrVelvetFog/source-review-coverage/pull/24).

`replay_merge()` in `tools/ceb.py` recomputes a recorded octopus merge commit by
folding its parents left, pairwise, through `git merge-tree --write-tree`. Whether that
reproduces what Git's own multi-parent `git merge` (the `octopus` strategy) would have
produced was open — §2 of the horizon brief carried it forward unresolved. It is not
proven in general, and `experiments/octopus_probe.sh` now falsifies it for one
well-defined case.

The probe generates random 3-to-5-parent merges — line edits, new files, deletions and
renames, with a tunable bias toward colliding edits — and compares the native `git
merge`'s result against the left fold, in the same parent order, on every trial the
native strategy accepted. Findings, reproducible with `experiments/octopus_probe.sh 120
12345`:

- With renames excluded, a 60-trial control agreed on all 60 trials the native strategy
  accepted: same clean/conflict outcome, identical resulting tree.
- With renames allowed, 120 trials produced 74 merges the native strategy accepted, of
  which the left fold reproduced 42 exactly and diverged on the other 32. Every one of
  the 32 involves the same shape: two branches renaming the same source path to two
  different destinations (a rename/rename(1:2)). Native octopus's per-parent step is a
  plain path-based three-way merge with no rename detection, so it accepts the result as
  two ordinary added files and one ordinary deletion — no conflict. The left fold's
  per-parent step uses `git merge-tree`, whose content-similarity rename detection
  reports `CONFLICT (rename/rename)` on the same input.

Practical consequence: a verifier replaying a real octopus merge commit that Git itself
produced cleanly can report a false `residual` (or an unresolved conflict) when that
merge's parents include a rename/rename(1:2) pair, even though nothing shipped that no
approval covers. No fix is proposed here — the probe's job was to answer the equivalence
question, not to close the gap — but this is the shape a fix or a documented limitation
would need to cover.

## Reproduced, and one step further (maintainer's note, 2026-09-09)

On macOS with Git 2.50.1 and bash 3.2 the same seed gives 29 disagreements out of 67
accepted merges rather than 32 of 74: bash 3.2 and bash 5 seed `RANDOM` differently, so a
seed reproduces a sequence only on the same bash. Three kept counterexamples, taken apart
by hand, were each the shape above, and Git names it at the fold step:

```
CONFLICT (rename/rename): b.txt renamed to renamed_br0.txt in 331badf… and to renamed_br2.txt in b36cc39…
```

Native octopus does no rename detection. `git merge-tree --write-tree -X no-renames`
matches it: with `FOLD_OPTS="-X no-renames"` the same 120 trials give 0 disagreements,
and each counterexample's fold tree becomes byte-identical to the octopus tree. So the
verifier's three-or-more-parent path has a one-line fix, and this probe is its test;
that is CE-019. The two-parent path keeps rename detection, because that is what the
forges' merge does.

The rename-free control is `RENAMES=0 experiments/octopus_probe.sh 60 12345`.
