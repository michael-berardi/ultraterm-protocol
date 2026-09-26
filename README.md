# UltraTerm Terminal Protocol (UTP)

<p align="center">
  <strong>A small, same-user control protocol that lets local agents see and drive persistent terminal sessions safely.</strong>
</p>

<p align="center">
  <a href="https://github.com/michael-berardi/ultraterm-protocol/releases/latest"><img src="https://img.shields.io/github/v/release/michael-berardi/ultraterm-protocol?label=release" alt="Latest release" /></a>
  <a href="LICENSE"><img src="https://img.shields.io/github/license/michael-berardi/ultraterm-protocol" alt="MIT License" /></a>
  <img src="https://img.shields.io/badge/wire-v2-blue" alt="Wire protocol v2" />
  <img src="https://img.shields.io/badge/dependencies-none-brightgreen" alt="No dependencies" />
</p>

<p align="center">
  <a href="#install">Install</a> ·
  <a href="#quick-look">Quick look</a> ·
  <a href="#commands">Commands</a> ·
  <a href="protocols/v2.md">Specification</a> ·
  <a href="#security">Security</a>
</p>

UTP is the local control interface of [UltraTerm](https://implosecybernetics.com/software/),
a terminal workspace for running coding agents side by side. It lets an agent
list the terminals on your machine, read a bounded slice of their output, send
input, open or close terminals, hand work to a fresh worker, and report back to
the agent that delegated it.

Everything happens over JSON Lines on a private Unix socket. There is no TCP
listener, no daemon to install and no runtime dependency beyond Python's
standard library.

- **Safe by default.** Every destructive command is a dry run until you confirm
  it with the exact session ID the dry run printed. A reused slot or stale ID is
  refused.
- **Identity, not slot numbers.** Manager and worker routes are pinned to the
  real agent conversations, so a renumbered or replaced terminal never receives
  someone else's work.
- **Nothing typed behind your back.** Completions and messages go to the
  agent's native inbox, never into a terminal as keystrokes.
- **Honest failures.** The client never retries on its own. When a mutation's
  outcome is unknown it says so and tells you how to reconcile.

## Install

UltraTerm installs and updates the reference client at `~/.ultraterm/bin/utp`.
Put that directory on your `PATH`:

```sh
export PATH="$HOME/.ultraterm/bin:$PATH"  # add to your shell profile to persist
```

To try the source client in this repository without replacing the managed
binary, link it under another name:

```sh
git clone https://github.com/michael-berardi/ultraterm-protocol.git
ln -s "$PWD/ultraterm-protocol/clients/python/utp" ~/.local/bin/utp-source
utp-source --version
```

Standalone `inspect` calls need `--no-uc` unless the bundled `uc` executable is
also available.

## Quick look

```sh
utp list                                   # terminals, profiles and session IDs
utp inspect --slot 2 --no-uc               # bounded recent output from slot 2
utp message --to 2 --expected-id SESSION_ID "Rebase onto main when you finish."
utp close --slot 3                         # dry run: prints the session ID
utp close --slot 3 --expected-id SESSION_ID --confirm
```

The current release is 2.2.1 (`utp --version`); the wire protocol is v2. See
the [changelog](CHANGELOG.md).

## Protocol v2

UTP v2 uses JSON Lines over `~/.ultraterm/utp.sock`. The directory is mode `0700`; the socket is mode `0600`; there is no TCP listener. Every success contains `"ok":true`; every failure contains `"ok":false` and a human-readable `error`.

The normative contract is [`protocols/v2.md`](protocols/v2.md). [`protocols/v1.md`](protocols/v1.md) remains the immutable 1.0 contract.

### Commands

| Client command | Behavior |
|---|---|
| `utp diagnose` | Read-only JSON diagnostics: release/wire versions, connection counts and bounded aggregate health counters; no terminal contents or private paths. |
| `utp list` | Read-only attached slot/session inventory. |
| `utp inspect --slot N` | Read-only bounded PTY history; model-readable UltraCompact output by default, or plain text with `--no-uc`. |
| `utp savings [--rate DOLLARS_PER_MILLION]` | Read local UltraCompact telemetry and summarize saved tokens for the day, 7 days, 30 days, and all time. |
| `utp send --slot N TEXT` | Explicit low-level PTY input. |
| `utp message --to N TEXT` | Durable inbox submission with receipt; `--notice-only` selects an ephemeral banner. A receipt records mailbox state only: neither proves native host acceptance, agent acknowledgment or that a model read the message. |
| `utp receipt RECEIPT_ID` | Read the stored state of one durable message or completion receipt. |
| `utp open --profile P` | Dry-run the lowest-free-slot assignment; confirmation attaches its pane. |
| `utp close --slot N` | Dry-run an exact slot removal; confirmation requires the printed session ID. |
| `utp switch-profile P --slot N` | Dry-run an identity-bound in-place profile handoff. |
| `utp register-manager --slot M --from-id WID --expected-id MID` | Register the exact worker and manager sessions (`WID` from `list`, `MID` from `list`); many workers may share one manager. |
| `utp task-done --from-id WID --summary TEXT` | Queue a completion to the registered manager conversation; `--to M` additionally requires `--expected-id MID`. Query its receipt for delivery state. |
| `utp handoff ...` | Transfer a private context packet to a replacement or new managed worker. |
| `utp profiles ...` | List harness-scoped profiles; create/remove require `--adapter omp`. |
| `utp report ...` | One authorized friendly text report, file, or image through a private local route hook. |
| `utp redact ...` | Delete the bot's own prior messages by explicit ID through the same hook; audit-logged. |

Profile creation may include a provider-neutral ordered routing list:

```sh
utp profiles create --adapter omp quality provider/model high \
  --routing upstream/primary,upstream/fallback
```

## Model-readable inspection and savings

The server always returns bounded PTY history. The reference client passes that
history through UltraCompact by default so agents receive a compact readable
packet; `utp inspect --no-uc` prints the server text unchanged. `utp savings`
reads the bundled UltraCompact telemetry locally and can add an estimated value
with `--rate`. Neither command sends terminal output or telemetry over a
network.

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
where that subcommand supports it; a slot never substitutes for a session ID.

## Native-identity manager registration

A manager route binds one worker session ID to one manager session ID and to the
native agent conversations behind them:

```sh
utp list
utp register-manager --slot 1 --from-id WORKER_SESSION_ID --expected-id MANAGER_SESSION_ID
utp task-done --from-id WORKER_SESSION_ID --summary "Focused regression suite passed."
```

Both IDs are required and are rejected when they no longer match the live
sessions, when a native conversation is unauthenticated, or when either session
is being replaced. Registration persists across an app restart and across slot
renumbering, and a newly created terminal never inherits a replaced one's route.
Completions are delivered only to the manager's native conversation inbox: they
are never typed into a PTY, and they are rejected once either pinned conversation
has changed, until the new assignment is registered explicitly. The local route
store at `~/.ultraterm/manager-map.json` is format version 3 while the wire
version stays 2, and legacy slot-only records are not migrated into it.

## Universal handoff

Create one private packet under `/tmp`, `chmod 600` it, and keep it at or below 16 KiB. Its path must not contain control characters, because the path is typed into the worker terminal. Include: Goal; Current state; Completed; every Remaining todo; Decisions and constraints; Resources and artifacts; Next action. Exclude credentials and obsolete transcript history.

Same-slot handoff dry run:

```sh
utp handoff --slot 3 --profile quality --packet /tmp/handoff.md --manager-slot 1
```

New managed worker dry run:

```sh
utp handoff --new-slot --profile quality --packet /tmp/handoff.md --manager-slot 1
```

After the user explicitly approves the exact plan, repeat with `--confirm --user-authorized`; same-slot handoff also requires the printed `--expected-id`. A confirmed handoff must run from the manager terminal or an external non-UltraTerm shell. The client waits for the receiving session to produce stable output, registers that exact worker session ID against the manager session ID from `list`, and only then submits a short instruction pointing to the packet. Packet submission is pinned to the captured worker session ID, so a slot whose identity changed is refused instead of typed into. Nothing is submitted when preparation fails; because no packet can be in flight then, the client closes the pane it just opened, bound to the session ID it opened, and reports the original error. If the submission itself is attempted but not confirmed (transport timeout, disconnect, malformed reply), the packet may already have been delivered: the client keeps that worker untouched and prints the session ID so the operator can inspect, adopt, or close it explicitly. One manager may repeat this flow for multiple independent workers; registrations and completions are never typed into a PTY, and the handoff instruction is the only PTY input.

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

Each repeated flag becomes one bullet. The recipient sees only the non-empty `What's new`, `What's changed`, and `Fixes` sections. Text reports reject paragraphs, technical workflow details, verification chatter, deployment mechanics, commit identifiers (including bare hashes), rollback instructions, and protected values such as credential-shaped tokens. The route is a local alias; a user-owned hook keeps destination IDs, provider authentication, project labels, and delivery outside UTP. The client invokes the executable at `~/.ultraterm/report-hook` (override with `UTP_REPORT_HOOK`) and sends the JSON payload on standard input. The hook must live in a directory you own with no group or other access (`chmod 700`).

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

## Diagnostics and lifecycle recovery

Run `utp diagnose` to check the control socket without inspecting terminal output.
An older server may reject this additive command; that does not change v2 compatibility.
The CLI bounds a reply to 1 MiB and the exchange to a 10-second deadline. It reports
missing/refused sockets, timeout, disconnect, truncated lines, invalid JSON, and invalid
reply envelopes without Python tracebacks. A missing/nonexecutable optional UC codec
is a clean error; use `inspect --no-uc` for plain text (no silent compression fallback).

The client never automatically retries a request. Before any request bytes are sent,
a connection failure means no request was sent. Once sending starts, a failed mutation
has an **unknown outcome**, even on timeout or malformed reply: do not blindly repeat
`send`, confirmed `open`/`close`/`switch-profile`, or a composed handoff. Use read-only
`diagnose`, `list`, and receipt lookup to reconcile first. Receipt IDs are useful only
with server-supported deduplication; do not infer arbitrary mutation idempotence.
Read-only queries can be retried manually after connectivity returns. Fresh dry runs
and session IDs are required before a newly authorized destructive operation.

An app restart or lifecycle interruption drops the control socket and every
connection, so clients MUST reconnect and obtain a fresh `list` before any
identity-bound `send`, `close`, `switch-profile` or handoff. For a harness
terminal the session ID is stored on the durable terminal session and survives
the restart and a slot renumber; a replaced, relaunched or closed terminal never
inherits an older identity, and a plain shell session gets a fresh ID. Fresh dry
runs and IDs are still required before a newly authorized destructive operation,
because the native agent conversation behind a terminal may have changed even
when its ID did not. Do not delete sockets, restart terminals, or replay work
automatically, and treat a stale registration as needing explicit
re-registration rather than reuse. Let the user restore the app, diagnose again,
and obtain a fresh inventory; report uncertainty if observed state cannot
establish the prior mutation's outcome. Diagnostics do not read prompts, terminal
contents, credentials, or private paths.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). The v1 contract is frozen; identity-bound orchestration is versioned as v2. Report vulnerabilities privately as described in [SECURITY.md](SECURITY.md).

## License

[MIT](LICENSE)
