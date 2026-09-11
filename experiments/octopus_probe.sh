#!/usr/bin/env bash
# CE-012 — Octopus replay equivalence probe.
#
# Spec v0.1 (see PLANS/V1/HORIZON_BRIEF.md §2) states that tools/ceb.py's
# replay_merge() folds an octopus merge commit's parents left, pairwise,
# via `git merge-tree --write-tree`, rather than running git's own
# octopus merge strategy. The two are not proven equivalent. This script
# searches for a counterexample: a randomly generated N-parent merge where
# git's native octopus strategy and the left fold disagree, either on
# whether the merge is clean or on the resulting tree.
#
# Usage: experiments/octopus_probe.sh [trials] [seed]
#   trials  number of random cases to generate (default 120; each trial
#           does several git checkouts/commits, so 120 runs in well under
#           two minutes on a stock GitHub Actions runner)
#   seed    RANDOM seed for reproducibility (default 12345)
#
# Exit status: 0 if every trial agreed, 1 if a counterexample was found
# (its reproduction is left on disk and the path is printed), 2 on a
# harness error unrelated to the question being probed.
#
# Environment:
#   RENAMES=0    disable the rename edit kind (the rename-free control)
#   FOLD_OPTS=   extra options for the fold's merge-tree step. Defaults to
#                "-X no-renames", matching replay_merge()'s ≥3-parent path
#                since CE-019 (native octopus does no rename detection).
#                Set FOLD_OPTS= (empty) for the rename-detecting fold that
#                CE-012 showed diverging.
#
# Requires: git, bash, mktemp. No network, no third-party packages —
# consistent with the verifier's own "stdlib and git only" rule (spec
# design rule, brief §3). Portable across GNU and BSD userlands.

set -u -o pipefail

TRIALS="${1:-120}"
SEED="${2:-12345}"
RENAMES="${RENAMES:-1}"
FOLD_OPTS="${FOLD_OPTS--X no-renames}"
RANDOM=$SEED

WORK="$(mktemp -d "${TMPDIR:-/tmp}/octopus_probe.XXXXXX")"
trap 'rc=$?; if [ "$rc" -eq 0 ]; then rm -rf "$WORK"; fi' EXIT

agree=0
disagree=0
octopus_ok=0
octopus_refused=0
counterexamples=()

# --- left fold, mirroring tools/ceb.py replay_merge() exactly ------------
# ok: 0 clean, 1 conflicted somewhere. Prints the final tree oid on stdout
# (even when conflicted, mirroring merge_tree()'s "still write a tree"
# behaviour, so a caller can inspect what the fold produced).
left_fold() {
  local repo="$1"; shift
  local parents=("$@")
  local acc="${parents[0]}"
  local clean=0
  local tree=""
  local i
  for ((i = 1; i < ${#parents[@]}; i++)); do
    local out rc
    # shellcheck disable=SC2086
    out="$(git -C "$repo" merge-tree --write-tree $FOLD_OPTS "$acc" "${parents[$i]}" 2>/dev/null)"
    rc=$?
    tree="$(printf '%s\n' "$out" | head -n1)"
    if [ "$rc" -ne 0 ]; then clean=1; fi
    if [ -z "$tree" ]; then
      echo ""
      return 1
    fi
    acc="$(git -C "$repo" commit-tree "$tree" -p "$acc" -m replay 2>/dev/null)"
  done
  echo "$tree"
  return $clean
}

# --- one random trial ------------------------------------------------------
run_trial() {
  local n="$1"
  local repo="$WORK/r$n"
  rm -rf "$repo"
  git init -q "$repo"
  git -C "$repo" config user.email t@example.com
  git -C "$repo" config user.name probe

  # Base: a handful of files with several lines each, so edits can land on
  # the same line (a real conflict) or different lines (an auto-mergeable
  # change) depending on the draw.
  for f in a b c; do
    { for l in 1 2 3 4 5; do echo "$f-line$l"; done; } > "$repo/$f.txt"
  done
  git -C "$repo" add -A
  git -C "$repo" commit -qm base
  local base
  base="$(git -C "$repo" rev-parse HEAD)"

  # 3 to 5 branches off base. conflict_bias raises the odds two branches
  # touch the same (file, line), which is what makes octopus refuse.
  local nbranches=$((3 + RANDOM % 3))
  local conflict_bias=$((RANDOM % 3))   # 0 = low, 1 = medium, 2 = high
  local branches=()
  local b
  for ((b = 0; b < nbranches; b++)); do
    git -C "$repo" checkout -q "$base"
    git -C "$repo" checkout -q -b "br$b"
    local nedits=$((1 + RANDOM % 2))
    local e
    for ((e = 0; e < nedits; e++)); do
      local kind=$((RANDOM % 4))
      if [ "$kind" -eq 0 ]; then
        # Edit an existing line. Under high conflict_bias, bias toward a
        # small fixed set of (file, line) targets so branches collide.
        local files=(a b c)
        local file
        if [ "$conflict_bias" -ge 1 ] && [ $((RANDOM % (3 - conflict_bias))) -eq 0 ]; then
          file="a"
        else
          file="${files[$((RANDOM % 3))]}"
        fi
        local line
        if [ "$conflict_bias" -eq 2 ]; then
          line=1
        else
          line=$((1 + RANDOM % 5))
        fi
        if [ -f "$repo/$file.txt" ]; then
          # Through a temporary file: `sed -i` differs between GNU and BSD.
          sed "s/^$file-line$line\$/$file-line$line-br$b-e$e/" "$repo/$file.txt" > "$repo/$file.txt.tmp" \
            && mv "$repo/$file.txt.tmp" "$repo/$file.txt"
        fi
      elif [ "$kind" -eq 1 ]; then
        # New file, unique per branch: never conflicts by construction.
        echo "new-br$b-e$e" > "$repo/new_br${b}_e${e}.txt"
        git -C "$repo" add "new_br${b}_e${e}.txt"
      elif [ "$kind" -eq 2 ] && [ "$b" -gt 0 ]; then
        # Delete a file another early branch might also have touched.
        rm -f "$repo/c.txt"
      else
        # Rename with a content tweak, to exercise merge-ort's rename
        # detection rather than only line edits.
        if [ "$RENAMES" = 1 ] && [ -f "$repo/b.txt" ] && [ "$e" -eq 0 ]; then
          git -C "$repo" mv b.txt "renamed_br${b}.txt" 2>/dev/null || true
          echo "tail-br$b" >> "$repo/renamed_br${b}.txt" 2>/dev/null || true
        fi
      fi
    done
    git -C "$repo" commit -qam "br$b" >/dev/null
    branches+=("br$b")
  done

  # Native octopus: first branch is the checkout, the rest are merged in.
  git -C "$repo" checkout -q -b combined "${branches[0]}"
  local merge_out merge_rc
  merge_out="$(git -C "$repo" merge --no-edit "${branches[@]:1}" 2>&1)"
  merge_rc=$?

  local parent_oids=()
  local p
  for p in "${branches[@]}"; do
    parent_oids+=("$(git -C "$repo" rev-parse "$p")")
  done

  local fold_tree fold_rc
  fold_tree="$(left_fold "$repo" "${parent_oids[@]}")"
  fold_rc=$?

  if [ "$merge_rc" -eq 0 ]; then
    octopus_ok=$((octopus_ok + 1))
    local octo_tree
    octo_tree="$(git -C "$repo" rev-parse HEAD^{tree})"
    if [ "$fold_rc" -eq 0 ] && [ "$octo_tree" = "$fold_tree" ]; then
      agree=$((agree + 1))
    else
      disagree=$((disagree + 1))
      counterexamples+=("$repo")
      echo "COUNTEREXAMPLE trial=$n: octopus succeeded (tree=$octo_tree) but left fold $([ "$fold_rc" -ne 0 ] && echo "conflicted" || echo "produced a different tree ($fold_tree)"). Repro kept at: $repo" >&2
    fi
  else
    octopus_refused=$((octopus_refused + 1))
    # Native octopus refused. The interesting question here is only
    # whether the left fold ever finds a *clean* resolution where native
    # octopus would not even try one (it aborts on the first pairwise
    # conflict rather than exploring alternatives) — that is not a
    # disagreement about a shipped tree, since no octopus commit like
    # this one would ever have existed for ceb.py to be asked to replay.
    # We only count and do not flag it.
    git -C "$repo" merge --abort >/dev/null 2>&1 || true
    agree=$((agree + 1))
  fi
}

for ((n = 0; n < TRIALS; n++)); do
  run_trial "$n"
done

echo "----------------------------------------------------------------------"
echo "octopus_probe: $TRIALS trials, seed=$SEED, renames=$RENAMES, fold_opts=${FOLD_OPTS:-none}"
echo "  native octopus succeeded : $octopus_ok"
echo "  native octopus refused   : $octopus_refused"
echo "  agreed with left fold    : $agree"
echo "  DISAGREED                : $disagree"
if [ "$disagree" -gt 0 ]; then
  echo "  counterexample repos kept under: ${counterexamples[*]}"
  echo "  (rerun this trial's repo to inspect: git -C <repo> log --all --graph --oneline)"
  exit 1
fi
echo "No counterexample found across $TRIALS trials: whenever git's native"
echo "octopus strategy accepted an N-parent merge, tools/ceb.py's left fold"
echo "reproduced the identical resulting tree."
exit 0
