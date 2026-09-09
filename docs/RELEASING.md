# Releasing

A release every fourteen days from v0.2.0 (2026-09-08): 09-22, 10-06, 10-20, and so on,
whether or not there is much in it. The cadence is the commitment; an entry that says
"no user-visible change" is a valid release. `v1` floats to the newest `0.x`, so
consumers on `@v1` pick each release up on their next run and do nothing.

## Checklist

1. **Changelog.** Move everything under `[Unreleased]` into `## [X.Y.Z] - YYYY-MM-DD`.
   Thank every contributor to the release by handle in the entry, on the line of the
   change they made. Leave `[Unreleased]` in place, empty.
2. **Version.** `VERSION` becomes `X.Y.Z`. Re-attest the examples against it:
   `xv run -m examples/manifest.json -o examples/attest.json` (from
   [verified-examples](https://github.com/DrVelvetFog/verified-examples)); commit the
   updated `examples/attest.json` with the rest as `release X.Y.Z`.
3. **Check.** `bash tools/release_check.sh --tag vX.Y.Z` must print `PASS`. It checks the
   action description is within the Marketplace's 125 characters (that one has bitten),
   branding is present, `VERSION` matches the newest changelog heading and the tag,
   `[Unreleased]` is empty, every example is attested against `X.Y.Z`, and the tree is
   clean.
4. **Land it.** Pull request, CI green, merge. The push-to-`main` run attests the release
   commit like any other.
5. **Tag.** On the merge commit:

   ```bash
   git tag -a vX.Y.Z -m "X.Y.Z"
   git tag -f v1 "$(git rev-parse vX.Y.Z^{commit})"   # the commit, not the tag object
   git push origin vX.Y.Z && git push -f origin v1
   ```

6. **Release page.** `gh release create vX.Y.Z --title "X.Y.Z — <one line>" --notes-file
   notes.md`. The notes are the changelog entry, the one-line install snippet, thanks by
   handle, and the closing line every outward text here ends with (below). Publishing
   the release runs [`release.yml`](../.github/workflows/release.yml), which runs the
   action at the tag and attaches the tag's own attestation (four files) to the release
   page; check they are there.
7. **Marketplace.** The listing at
   [marketplace/actions/source-review-coverage](https://github.com/marketplace/actions/source-review-coverage)
   updates itself from the release. Confirm it shows `X.Y.Z`.
8. **One consumer.** Trigger or wait for one run on a repository pinned to `@v1`
   ([field notes](field-notes.md) lists three) and confirm it is green on the new code.

## The closing line

> A pass establishes review coverage and nothing else: not correctness, not that a human
> read anything, not truthful authorship, not reviewer independence, not existence at a
> time, not compliance.
