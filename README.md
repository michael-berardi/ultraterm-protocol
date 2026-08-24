# UltraTerm Terminal Protocol

UltraTerm Terminal Protocol (UTP) lets local agents inspect and control persistent terminal sessions without GUI automation. Agents can address a stable terminal slot, read recent output, send input, delegate work, and report completion through one same-user Unix socket.

## Install the reference client

From this repository:

```sh
mkdir -p "$HOME/.ultraterm/bin"
chmod +x clients/python/utp
ln -sfn "$(pwd)/clients/python/utp" "$HOME/.ultraterm/bin/utp"
export PATH="$HOME/.ultraterm/bin:$PATH"
```

UltraTerm vendors this stdlib-only Python client. UltraTerm must be running before the client can connect.

## Protocol v1

UTP v1 uses JSON Lines over `~/.ultraterm/utp.sock`. The directory is mode `0700`; the socket is mode `0600`. Each UTF-8 line contains one JSON request object and receives one JSON response object. The transport is a Unix domain socket only. It is never TCP.

All successful responses contain `"ok":true`. All failures use this shape:

```json
{"ok":false,"error":"human-readable error"}
```

The normative requirements and limits are in [`protocols/v1.md`](protocols/v1.md).

### `list`

```json
{"cmd":"list"}
{"ok":true,"sessions":[{"id":"SESSION_UUID","slot":1,"title":"Terminal 1","pid":12345,"launchedOmp":true,"launchProfile":"PROFILE_NAME"}]}
```

`launchProfile` is a string or `null`.

### `inspect`

Select by `id` or `slot`. `lines` defaults to `80` and is capped at `1000`; `raw` defaults to `false`.

```json
{"cmd":"inspect","slot":2,"lines":80,"raw":false}
{"ok":true,"id":"SESSION_UUID","text":"recent terminal output"}
```

### `send`

Select by `id` or `slot`. `enter` defaults to `true` and appends carriage return for terminal submission.

```json
{"cmd":"send","slot":2,"text":"run the focused test","enter":true}
{"ok":true,"id":"SESSION_UUID"}
```

### `message`

Messages are addressed banners, never broadcasts. `text` is limited to 4,000 Unicode characters.

```json
{"cmd":"message","from":1,"to":2,"text":"Tests are green."}
{"ok":true}
```

### `open`

`confirm` defaults to `false`. A dry run allocates nothing and reports the lowest free slot from 1 through 8.

```json
{"cmd":"open","profile":"PROFILE_NAME","title":"Worker","confirm":false}
{"ok":true,"confirmed":false,"would":{"slot":2,"profile":"PROFILE_NAME","title":"Worker"}}
```

A confirmed request returns the created session:

```json
{"cmd":"open","profile":"PROFILE_NAME","title":"Worker","confirm":true}
{"ok":true,"confirmed":true,"session":{"id":"SESSION_UUID","slot":2,"title":"Worker","pid":12345,"launchedOmp":true,"launchProfile":"PROFILE_NAME"}}
```

### `close`

`confirm` defaults to `false` and the target is selected by `slot`.

```json
{"cmd":"close","slot":2,"confirm":false}
{"ok":true,"confirmed":false,"would":{"slot":2,"id":"SESSION_UUID"}}
```

A confirmed request returns:

```json
{"cmd":"close","slot":2,"confirm":true}
{"ok":true,"confirmed":true,"closed":{"slot":2,"id":"SESSION_UUID"}}
```

### `register-manager`

The CLI command `register-manager` sends the wire command `register.manager`. `from` is the worker slot, normally read from `ULTRATERM_SLOT`; `to` is the manager slot.

```json
{"cmd":"register.manager","from":2,"to":1}
{"ok":true,"from":2,"managerSlot":1}
```

### `task-done`

The CLI command `task-done` sends the wire command `task.done`. `to` is optional when the worker has registered a manager. The server trims `text`, types it into the manager PTY with Enter, and emits an addressed banner.

```json
{"cmd":"task.done","from":2,"text":"Regression suite passed."}
{"ok":true,"deliveredTo":1,"typedIntoPty":true}
```

An explicit manager override uses:

```json
{"cmd":"task.done","from":2,"to":3,"text":"Regression suite passed."}
{"ok":true,"deliveredTo":3,"typedIntoPty":true}
```

## Local report hooks

`utp report` sends a structured project report to a user-installed local hook:

```sh
utp report \
  --project sample-product \
  --summary "The feature is available." \
  --verification "The focused workflow passed." \
  --rollback "Restore the previous verified build."
```

The hook defaults to `~/.ultraterm/report-hook`; `UTP_REPORT_HOOK` may select a
different path. The client requires the hook and its containing directory to
be owned by the current user. The directory must be private; the hook must be
a regular executable file that is not group/world writable.

`report` is a local CLI extension, not a UTP v1 wire command. It never sends
credentials or report content through the UltraTerm socket. The hook owns any
external authentication and delivery behavior.

## Agent onboarding

```sh
export PATH="$HOME/.ultraterm/bin:$PATH"
export ULTRATERM_SLOT=2
utp list
utp register-manager --slot 1
utp inspect --slot 1 --lines 40
utp task-done --summary "Onboarding complete."
```

Use [`examples/manager-delegate.sh`](examples/manager-delegate.sh) and [`examples/worker-complete.sh`](examples/worker-complete.sh) as complete shell examples.

## Security

UTP can write directly to terminal PTYs. Exposing that capability over TCP would turn a local convenience interface into a remote command-execution boundary requiring authentication, encryption, authorization, replay protection, and network hardening. UTP intentionally has none of those network features.

Implementations must use the same-user Unix socket, enforce `0700` on `~/.ultraterm`, enforce `0600` on `utp.sock`, and never bind, proxy, or forward UTP over TCP. Keep credentials in the user's environment or keychain; never place them in protocol messages, examples, issues, or commits.

## Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md). Protocol changes must preserve the v1 wire contract or ship under a new version.