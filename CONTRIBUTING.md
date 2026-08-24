# Contributing

Contributions should keep UTP small, local, and interoperable.

1. Open an issue describing the protocol or client problem.
2. Preserve the v1 wire contract. Put incompatible wire changes in a new versioned specification.
3. Keep the reference client compatible with the Python standard library. Do not add runtime dependencies.
4. Include no credentials, personal paths, terminal transcripts, private profiles, or internal operations material.
5. Do not add GitHub Actions. Run validation locally.

Before submitting a change:

```sh
python3 -m py_compile clients/python/utp
sh -n examples/manager-delegate.sh
sh -n examples/worker-complete.sh
gitleaks dir . --redact --no-banner
```

Update `README.md` and the applicable file under `protocols/` when behavior changes.