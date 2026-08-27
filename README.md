# UltraTerm Terminal Protocol

UltraTerm Terminal Protocol (UTP) lets local agents inspect and control persistent terminal slots, hand work between profiles and workers, coordinate managers with multiple workers, and send authorized friendly reports through one same-user local interface.

## Install the reference client

UltraTerm installs and updates the client at `~/.ultraterm/bin/utp` during
setup. Put that app-managed directory on your PATH:

```sh
export PATH="$HOME/.ultraterm/bin:$PATH"  # add to your shell profile to persist
```

Do not overwrite the app-managed binary. To try the checked-in source client,
link `clients/python/utp` under a different name or location such as
`$HOME/.local/bin/utp-source`.

UltraTerm must be running for socket commands. The checked-in stdlib-only
Python client is the public reference source for the installed client.

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
| `utp profiles ...` | List, create, or remove universal OMP profiles. |
| `utp report ...` | One authorized friendly text report, file, or image through a private local route hook. |
| `utp redact ...` | Delete the bot's own prior messages by explicit ID through the same hook; audit-logged. |

Profile creation may include a provider-neutral ordered routing list:

```sh
utp profiles create quality provider/model high \
  --routing upstream/primary,upstream/fallback
```

## Identity-bound slot lifecycle

Destructive commands are dry-run by default. The dry run returns the current session ID; confirmation must bind to it:

```sh
utp close --slot 3
utp close --slot 3 --expected-id SESSION_ID --confirm

utp switch-profile quality --slot 3
utp switch-profile quality --slot 3 --expected-id SESSION_ID --confirm
```

A reused slot or stale ID is rejected without changing the current terminal. Confirmed `open` assigns and attaches a slot. Confirmed `close` removes that exact slot and pane. Profile switching preserves slot, cwd, title, and dimensions, attaches the replacement before its startup health check, and repaints every live pane through the same appearance-refresh path used by theme changes.

Inside an UltraTerm tmux pane, the client discovers the caller slot from the
session name. External shells can identify a caller explicitly with `--from`
where that subcommand supports it.

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

After the user explicitly approves the exact plan, repeat with `--confirm --user-authorized`; same-slot handoff also requires the printed `--expected-id`. A confirmed handoff must run from the manager terminal or an external non-UltraTerm shell. The client waits for the receiving OMP session, then submits a short instruction pointing to the packet. One manager may repeat this flow for multiple independent workers.

Agents may suggest a handoff or an additional worker when a dry run reports free capacity and observed system memory is comfortable. They must never infer permission to open, close, replace, or hand off a terminal.

## Universal friendly reports

`utp report` is the single-call path for user-requested Telegram, bot, group, or generic project updates:

```sh
utp report \
  --route team:group-alias \
  --project project-name \
  --new "A new capability is now available." \
  --new "A second addition is ready to use." \
  --changed "An existing experience is easier to use." \
  --fixed "A user-visible problem no longer occurs." \
  --user-authorized
```

Each repeated flag becomes one bullet. The recipient sees only the non-empty `What's new`, `What's changed`, and `Fixes` sections. Text reports reject paragraphs, technical workflow details, verification chatter, deployment mechanics, commit identifiers, rollback instructions, and protected values. The route is a local alias; a user-owned hook keeps destination IDs, provider authentication, project labels, and delivery outside UTP. The client invokes the executable at `~/.ultraterm/report-hook` (override with `UTP_REPORT_HOOK`) and sends the JSON payload on standard input.

### Files and images

`--kind report` (the default) sends the structured update above. `--kind file` and `--kind image` deliver a single file instead:

```sh
utp report \
  --route team:group-alias \
  --project project-name \
  --kind file \
  --file /path/to/archive.zip \
  --summary "Optional caption." \
  --user-authorized
```

`--kind file|image` requires `--file`: a regular, non-empty file up to 45 MiB, sent by its resolved path. `--summary` is an optional caption of at most 1024 characters. `--new`, `--changed`, and `--fixed` apply only to text reports.

### Redacting prior messages

`utp redact` deletes the bot's own previously sent messages by explicit message ID:

```sh
utp redact \
  --route team:group-alias \
  --project project-name \
  --message-id 123 \
  --message-id 124 \
  --reason "Why deletion is prudent." \
  --user-authorized
```

Redaction deletes only the bot's own messages, only by explicit `--message-id` (1-20 per call, duplicates removed), and requires `--user-authorized` plus a 1-300 character `--reason`. The hook resolves the chat, deletes each message independently so one failure does not stop the rest, and writes a fail-open audit entry for every call.

## Security

UTP is command-capable. Servers must enforce the same-user Unix socket, directory mode `0700`, socket mode `0600`, bounded inputs, root-confined profile operations, identity-bound destructive confirmation, and symlink-safe private handoff packets. Never expose, proxy, or forward UTP over a network. Never place credentials, destination IDs, or private customer data in protocol traffic, examples, logs, fixtures, issues, or commits.

## Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md). V1 remains frozen; generalized identity-bound orchestration is versioned as v2.
