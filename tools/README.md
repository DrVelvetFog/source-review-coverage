# Reference implementation

`ceb.py` — issues and verifies `source-review-coverage` attestations.

```
python ceb.py record --base <ref> --reviewed-head <ref> --merged <ref> > record.json
python ceb.py intoto record.json > statement.json
python ceb.py verify record.json --statement statement.json \
    --bundle statement.sigstore.json --signer-repo owner/name
```

Python 3 and `git`, no third-party packages, no network. Signature verification
additionally requires the `sigstore` package; without it the verifier reports
`INCOMPLETE` rather than passing an unchecked claim.

The signer is expected to be a workflow identity, not a developer — see R4 in the
specification, and `.github/workflows/attest.yml` for a working example.
