# Source Review Coverage

An [in-toto attestation](https://github.com/in-toto/attestation) predicate carrying the
evidence needed to decide, independently of the system that produced it, whether a source
revision was covered by the review it claims.

SLSA v1.2 Source Track Level 4 requires that changes to protected branches be agreed to by
two or more trusted persons, and requires this of *the final revision submitted*. That
requirement has no verifier: SLSA leaves source provenance attestations undefined, and does
not address how squash merges or rebases interact with approval. In practice the Source
Control System asserts the property to a consumer who cannot check it.

This predicate replaces the assertion with something recomputable — which tree each approval
covered, which tree shipped, and how one became the other.

## Versions

- [**v0.1**](v0.1/) — `https://drvelvetfog.github.io/source-review-coverage/v0.1`

## Status

Draft. Not yet submitted to the in-toto attestation framework for vetting.

## What a passing result does not establish

Not correctness. Not that a human read anything. Not truthful authorship. Not independence
of the signers. Not existence at a stated time. And not compliance with any regulation — a
record may be evidence submitted toward an obligation, never a certificate of meeting one.
