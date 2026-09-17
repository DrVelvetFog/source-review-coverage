# Checking an attestation somewhere else

```bash
gh run download <run-id> -n source-review-coverage-attestation -D att    # the artifact
pip install sigstore                                                      # signature check only
python tools/ceb.py verify-artifact att --repo /path/to/clone --signer-repo owner/name
```
Exit `0` verified · `1` unverified, the report names why · `2` incomplete, a claim could not be checked · `3` malformed.
Every line is recomputed: the shipped tree, the replay of what was approved, the signature and whose workflow held the key,
and that the statement is exactly what the record produces. Your clone is not written to (`--allow-write` replays in place).
