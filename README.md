# UltraTerm Terminal Protocol (UTP)

UTP lets local agents inspect and control [UltraTerm](https://paretocybernetics.com/software/)
terminal sessions over a private Unix socket. The reference CLI uses only Python’s standard library.
Session IDs bind destructive operations to a specific terminal; bounded reads
and receipt lookup help agents reconcile failures without replaying work.

This repository contains the client and wire specifications, not the server.
A running UltraTerm installation provides the server. The client requires
Python 3 and a platform with Unix-domain sockets (tested with Python 3.15).

## Install

Download the single-file client; no package installation is needed:

```sh
curl -fsSL https://raw.githubusercontent.com/michael-berardi/ultraterm-protocol/v2.9.0/clients/python/utp -o utp
python3 - <<'PY'
import hashlib
from pathlib import Path

expected = "10919f0b7c5849471b3fdff5294b1e17197495f37d2adb5fc470975c1f1e1360"
actual = hashlib.sha256(Path("utp").read_bytes()).hexdigest()
if actual != expected:
    raise SystemExit(f"utp checksum mismatch: expected {expected}, got {actual}")
PY
python3 utp --version
```

The URL is pinned to release **2.9.0**; the SHA-256 check verifies the downloaded client before you run it.

### From source

```sh
git clone https://github.com/michael-berardi/ultraterm-protocol.git
python3 ultraterm-protocol/clients/python/utp --version
```

For a checkout, use that client path in place of `utp` below. UltraTerm also
manages a client at `~/.ultraterm/bin/utp`; you can run that path directly.

## First use

With UltraTerm running, these commands only read session state:

```sh
python3 utp list
python3 utp inspect --slot 2 --lines 80
python3 utp diagnose
```

Use the slot returned by `list`. Closing or replacing a session starts with a
dry run; confirmation must bind to the session ID it printed:

```sh
python3 utp close --slot 3
python3 utp close --slot 3 --expected-id SESSION_ID --confirm
```

`send`, native messages and reports are not dry runs. Use them only with
explicit authority. Opening a terminal requires a harness choice:

```sh
python3 utp open --harness HARNESS --profile PROFILE
```

That command is a dry run; add `--confirm` only after approval. `UTP_HARNESS`
can supply the harness instead.

## Updates

On a terminal, `utp` says when a newer release exists. `utp update` installs it after
verifying its SHA-256 checksum, and `utp update --check` only reports. Automatic
installation is off until you turn it on. See [docs/updates.md](docs/updates.md).

## Privacy

UTP has no telemetry. Commands talk only to UltraTerm's same-user Unix socket.
On a terminal it makes one anonymous request a day for the public latest-release record,
sending no version, identifier or usage data; it stays silent in CI, agents and scripts.
Turn it off with `UTP_NO_UPDATE_CHECK=1` or `utp update --checks off`.
It stores only update state in your cache folder; `utp update --auto off` deletes it.
Details, including update downloads and rollback: [PRIVACY.md](PRIVACY.md).

## Reference

- [Commands, handoffs, reports and recovery](docs/usage.md)
- [Privacy and local state](PRIVACY.md)
- [Normative v2 specification](protocols/v2.md) and [frozen v1 contract](protocols/v1.md)
- `utp --help` and `utp COMMAND --help` for client flags
- [Changelog](CHANGELOG.md)

The client never retries requests automatically. After a transport failure,
a mutation may have happened: reconcile with read-only queries before taking
further action. Receipt waits and dial catalog queries have longer deadlines
than the default 10-second exchange.

## Security

UTP is command-capable and same-user only. The socket directory must be mode
`0700`, and the socket mode `0600`. Never proxy it onto a network. Keep
credentials, private terminal output and destination IDs out of issues and
fixtures. See the [security policy](SECURITY.md) for private reporting.

## Development

No third-party runtime dependencies are required. Run the local checks in
[CONTRIBUTING.md](CONTRIBUTING.md); tests use synthetic fixtures and disposable
sockets rather than a running app. The server implementation is outside this
repository, so these tests do not verify its behavior.

## License

[MIT](LICENSE)

---

Part of [Pareto Cybernetics](https://paretocybernetics.com/projects/ultraterm-protocol/): free, private, open-source tools for working with AI agents.
