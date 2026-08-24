# UltraTerm Terminal Protocol

UltraTerm Terminal Protocol (UTP) lets local agents inspect and control persistent terminal slots, hand work between profiles and workers, coordinate managers with multiple workers, and send authorized friendly reports through one same-user local interface.

## Install the reference client

```sh
mkdir -p "$HOME/.ultraterm/bin"
chmod +x clients/python/utp
ln -sfn "$(pwd)/clients/python/utp" "$HOME/.ultraterm/bin/utp"
export PATH="$HOME/.ultraterm/bin:$PATH"
```

UltraTerm vendors this stdlib-only Python client. UltraTerm must be running for socket commands.

## Protocol v2

UTP v2 uses JSON Lines over `~/.ultraterm/utp.sock`. The directory is mode `0700`; the socket is mode `0600`; there is no TCP listener. Every success contains `"ok":true`; every failure contains `"ok":false` and a human-readable `error`.

The normative contract is [`protocols/v2.md`](protocols/v2.md). [`protocols/v1.md`](protocols/v1.md) remains the immutable 1.0 contract.

| Client command | Behavior |
|---|---|
| `utp list` | Read-only attached slot/session inventory. |
| `utp inspect --slot N` | Read-only bounded PTY history, not reconstructed screen state. |
| `utp send --slot N TEXT` | Explicit low-level PTY input. |
| `utp message --to N TEXT` | Neutral addressed notice; no prompt input or broadcast. |
| `utp open --profile P` | Dry-run the lowest-free-slot assignment; confirmation attaches its pane. |
| `utp close --slot N` | Dry-run an exact slot removal; confirmation requires the printed session ID. |
| `utp switch-profile P --slot N` | Dry-run an identity-bound in-place profile handoff. |
| `utp register-manager --slot M --from W` | Register worker W to manager M; many workers may share one manager. |
| `utp task-done --from W --summary TEXT` | Deliver worker completion to its manager notice and PTY. |
| `utp handoff ...` | Transfer a private context packet to a replacement or new managed worker. |
| `utp profiles ...` | Root-confined universal OMP profile management. |
| `utp report ...` | One authorized friendly report through a private local route hook. |

## Identity-bound slot lifecycle

Destructive commands are dry-run by default. The dry run returns the current session ID; confirmation must bind to it:

```sh
utp close --slot 3
utp close --slot 3 --expected-id SESSION_ID --confirm

utp switch-profile quality --slot 3
utp switch-profile quality --slot 3 --expected-id SESSION_ID --confirm
```

A reused slot or stale ID is rejected without changing the current terminal. Confirmed `open` assigns and attaches a slot. Confirmed `close` removes that exact slot and pane. Profile switching preserves slot, cwd, title, and dimensions, attaches the replacement before its startup health check, and repaints every live pane through the same appearance-refresh path used by theme changes.

## Universal handoff

Create one private packet under `/tmp`, `chmod 600` it, and keep it at or below 16 KiB. Include: Goal; Current state; Completed; every Remaining todo; Decisions and constraints; Resources and artifacts; Next action. Exclude credentials and obsolete transcript history.

Same-slot handoff dry run:

```sh
utp handoff --slot 3 --profile quality --packet /tmp/handoff.md --manager-slot 1
```

New managed worker dry run:

```sh
utp handoff --new-slot --profile quality --packet /tmp/handoff.md --manager-slot 1
```

After the user explicitly approves the exact plan, repeat with `--confirm --user-authorized`; same-slot handoff also requires the printed `--expected-id`. The client waits for the receiving OMP session, then submits a short instruction pointing to the packet. One manager may repeat this flow for multiple independent workers.

Agents may suggest a handoff or an additional worker when a dry run reports free capacity and observed system memory is comfortable. They must never infer permission to open, close, replace, or hand off a terminal.

## Universal friendly reports

`utp report` is the single-call path for user-requested Felix, Telegram, bot, group, or generic reports:

```sh
utp report \
  --route felix:group-alias \
  --project project-name \
  --summary "Friendly one-line result." \
  --verification "Exact proof observed." \
  --rollback "Concrete rollback path." \
  --user-authorized
```

The route is a local alias. A user-owned hook holds chat IDs, bot tokens, provider authentication, formatting, and delivery logic outside UTP. After verified work, send once through UTP; do not duplicate the message through a browser or provider API.

## Security

UTP is command-capable. Servers must enforce the same-user Unix socket, directory mode `0700`, socket mode `0600`, bounded inputs, root-confined profile operations, identity-bound destructive confirmation, and symlink-safe private handoff packets. Never expose, proxy, or forward UTP over a network. Never place credentials, destination IDs, or private customer data in protocol traffic, examples, logs, fixtures, issues, or commits.

## Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md). V1 remains frozen; generalized identity-bound orchestration is versioned as v2.
