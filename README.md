# Source Review Coverage

An [in-toto attestation](https://github.com/in-toto/attestation) predicate carrying the
evidence needed to decide, independently of the system that produced it, whether a source
revision was covered by the review it claims.

**Type URI:** `https://drvelvetfog.github.io/source-review-coverage/v0.1`

- [Specification (v0.1)](v0.1/index.md)
- [Protobuf definition](v0.1/source_review_coverage.proto)

## Why

SLSA v1.2 Source Track Level 4 requires that changes to protected branches be agreed to by
two or more trusted persons, and requires this of *the final revision submitted*. That
requirement has no verifier: SLSA leaves source provenance attestations undefined, and does
not address how squash merges or rebases interact with approval. So the property is asserted
by the same system that performed the merge, to a consumer who cannot check it.

This predicate replaces the assertion with something recomputable — which tree each approval
covered, which tree shipped, and how one became the other. Where they cannot be reconciled,
a verifier emits the specific bytes that shipped with no approval covering them.

## Status

Draft. Not yet submitted to the in-toto attestation framework for vetting.

Apache-2.0.
