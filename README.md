# UltraTerm Terminal Protocol (UTP)

[![Latest release](https://img.shields.io/github/v/release/michael-berardi/ultraterm-protocol?label=release)](https://github.com/michael-berardi/ultraterm-protocol/releases/latest)
[![MIT License](https://img.shields.io/github/license/michael-berardi/ultraterm-protocol)](LICENSE)
![Wire protocol v2](https://img.shields.io/badge/wire-v2-blue)
![No dependencies](https://img.shields.io/badge/dependencies-none-brightgreen)

UTP lets local agents inspect and control UltraTerm terminal sessions over a
private Unix socket. The reference CLI uses only Python’s standard library.
Session IDs bind destructive operations to a specific terminal; bounded reads
and receipt lookup help agents reconcile failures without replaying work.

This repository contains the client and wire specifications, not the server.
A running UltraTerm installation provides the server. The client requires
Python 3 and a platform with Unix-domain sockets (tested with Python 3.15).

## Install

UltraTerm manages its client at `~/.ultraterm/bin/utp`. Add it to your shell’s
`PATH`:

```sh
export PATH="$HOME/.ultraterm/bin:$PATH"
```

For a source checkout, no package installation is needed:

```sh
git clone https://github.com/michael-berardi/ultraterm-protocol.git
python3 ultraterm-protocol/clients/python/utp --version
```

The client release is **2.8.3**; the wire protocol remains **v2**. To keep the
source client separate from the managed client, run it by the path above.

## First use

With UltraTerm running, these commands only read session state:

```sh
utp list
utp inspect --slot 2 --lines 80
utp diagnose
```

Use the slot returned by `list`. Closing or replacing a session starts with a
dry run; confirmation must bind to the session ID it printed:

```sh
utp close --slot 3
utp close --slot 3 --expected-id SESSION_ID --confirm
```

`send`, native messages and reports are not dry runs. Use them only with
explicit authority. Opening a terminal requires a harness choice:

```sh
utp open --harness HARNESS --profile PROFILE
```

That command is a dry run; add `--confirm` only after approval. `UTP_HARNESS`
can supply the harness instead.

## Reference

- [Commands, handoffs, reports and recovery](docs/usage.md)
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
