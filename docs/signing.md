# Signing: how, and why the envelope is detached

Every attestation is signed keylessly with the workflow's own identity: the job's
ambient GitHub OIDC token, through Sigstore (`sigstore==4.5.0`, pinned; the only
package the action installs). No developer key is involved, which is rule R4 — a
record signed by the party being audited is an assertion, and binding the signature
to a workflow identity is what makes it evidence. The job needs
`permissions: id-token: write`; a fork pull request has no token, so the run is
downgraded to unsigned with a warning and the verdict can be at best `INCOMPLETE`.

## The envelope

The natural shape for a signed in-toto Statement is a DSSE envelope
(`application/vnd.in-toto+json`). This action signs the statement as an
**artifact** instead — the signature is over the exact bytes of `statement.json`,
carried in the same Sigstore bundle. Same key custody, same transparency-log
entry, same identity binding; one less layer of typing.

The reason is upstream: sigstore-python validates in-toto Statements against a
digest set of `sha256/384/512` and the SHA-3 family only, and rejects any other
key (`sigstore/dsse/__init__.py`, `Digest = Literal[...]`). That includes
`gitCommit` and `gitTree`, which the in-toto attestation framework itself
defines — and the tree hash is the subject this predicate exists to name. The
presence of the unknown key is the rejection; adding a `sha256` digest alongside
does not help. The restriction is deliberate on their side
(sigstore/sigstore-python#1018 keeps the default set aligned with Sigstore's
algorithm registry, and git digests are SHA-1-shaped), so this is a conversation
about an opt-in, not a bug report. That conversation is CE-013 (#13), filed
upstream as sigstore/sigstore-python#1899.

## Reverting automatically

`ceb.py verify_bundle` tries the DSSE path first and falls back to the detached
shape only when DSSE verification fails and a statement file is present. The
verify output names which shape passed. If upstream accepts git digest types,
newly signed DSSE envelopes verify through the first path with no change here —
the fallback is written to make itself obsolete.

What a signature does establish: key custody, byte integrity, and which workflow
identity held the key. What it does not: anything about the signer's honesty
(specification §6).
