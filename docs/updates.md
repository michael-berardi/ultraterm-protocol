# Updates

<!-- update-contract: v1 -->

The reference client says when a newer release exists and updates itself in one step.
Updating never changes the wire protocol, and `utp update` never uses the UltraTerm socket.

## Commands

| Command | Result |
|---|---|
| `utp update` | Shows current → new and the first release-note lines, asks `Install <new> now? [Y/n]` on a terminal, then installs. Off a terminal it installs without asking. |
| `utp update --check` | Report only. Exit `0` current, `10` update available, `1` check failed (the cause is printed). |
| `utp update --skip` | No notice for this version; a newer one notifies again. |
| `utp update --auto on\|off\|status` | Automatic installation, off by default. `off` also deletes the update state and log; only a `--checks off` choice is kept. |
| `utp update --checks on\|off\|status` | The daily check, on by default. |
| `utp update --rollback` | Restores the client replaced by the last update and skips the version it removed. |

After an interactive install, if automatic installation is off, `utp update` asks once:
`Install future updates automatically? [y/N]`. The answer is remembered.

## Notice

After a command succeeds on a terminal, at most once a day per version, stderr shows:

```text
utp 2.10.0 available (you have 2.9.0) · run: utp update
turn on automatic updates: utp update --auto on · skip: utp update --skip
```

It is never written to stdout, so JSON Lines output stays clean. There is no check and no
notice when stdout or stderr is not a terminal, when `CI` or `CLAUDECODE` is set, with
`UTP_NO_UPDATE_CHECK=1`, or after `utp update --checks off`.

With automatic installation on, the check that finds a release installs it instead, in a
detached low-priority process; the new client applies on the next run. A failed automatic
install leaves the current client working, is reported by `utp update --auto status`, and
the notice returns.

## The check

One anonymous GET of the repository's public GitHub latest-release record, with the fixed
User-Agent `utp-update-check`, runs in the background beside your command (4 s timeout). It
sends no version, identifier or machine data. Only stable `x.y.z` releases newer than yours
count; drafts, prereleases and unparseable tags are ignored. The result, or the failure
cause, is kept in one `0600` file: `~/Library/Caches/utp/update.json` on macOS,
`$XDG_CACHE_HOME/utp/update.json` (default `~/.cache/utp`) elsewhere. See
[PRIVACY.md](../PRIVACY.md).

## Install safety

`utp update` downloads `clients/python/utp` and `clients/python/SHA256SUMS` from the release
tag, for example
`https://raw.githubusercontent.com/michael-berardi/ultraterm-protocol/v2.9.0/clients/python/utp`.
It checks the SHA-256 and the version inside the file, and only then swaps the file
atomically. The replaced file is kept as `<client>.previous` for `--rollback` and deleted
after the new client's first successful run, or after seven days. The download directory is
removed on success and on failure. The automatic-install log (`update.log` beside the state
file) stays under 256 KB.

| Install | `utp update` |
|---|---|
| Downloaded single file | Verified in-place update, as above. |
| Git checkout (`clients/python/utp` in a clone) | Runs `git -C <clone> pull --ff-only`; tracked files are never rewritten. |
| UltraTerm's copy (`~/.ultraterm/bin/utp`) | Updates with UltraTerm: no notice, and `utp update` says so. |

UTP is not published to Homebrew, npm, PyPI or crates.io.

## Uninstall

Run `utp update --auto off`, which deletes the update state and log, then delete the client
file (and `utp.previous`, if present).

## Releasing

Each client release regenerates the committed checksum before tagging, so the tag carries
both files:

```sh
shasum -a 256 clients/python/utp > clients/python/SHA256SUMS
git commit -am "Release X.Y.Z" && git tag vX.Y.Z
```

`tests/test_updates.py` fails while the checksum is stale.
