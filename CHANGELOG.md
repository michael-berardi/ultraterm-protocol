# Changelog

All notable changes are documented here. This project follows Keep a Changelog and Semantic Versioning.

## [2.6.1] - 2026-10-11

Corrects the 2.6.0 documentation against the UltraTerm 3.2.10 server source and fixes the reference client and its tests. The wire version stays 2; no command or field changed.

### Fixed

- Spec 3.13 no longer says `open` and `profile.switch` refuse a hidden profile with `HiddenProfileError:`. For a non-OMP harness, `open` returns the `unknown UltraTerm Profile` error for a hidden profile; OMP profiles and `profile.switch` are not checked against visibility yet (see Known issues). The 2.6.0 entry below repeats the wrong claim; this entry supersedes it.
- Spec 3.13 no longer says a missing profile falls back to the first visible one; `open` requires `profile`. `hidden` lists only profiles hidden in Settings, not profiles hidden because their provider was removed.
- Spec 3.13 says the hidden list is sorted by its `harness/profile` text, which is the server's order.
- Spec 3.14 upsert example is a built-in dial with `builtinProvider` equal to its `id`, and its reply is a non-empty catalog. Built-in dials accept only label, visibility and order edits; an `http` dial needs an endpoint and at least one window. An unknown `id` is appended, up to 34 dials.
- Spec 3.14 says `Invalid provider dial configuration` is for a wrong shape only; content-rule failures return specific messages.
- Spec §9 says the client's deadline is 50 seconds for `provider.dials` calls, not 10.

### Changed

- `utp dials enable|disable --confirm` checks the reply to a confirmed save: a reply without a valid catalog is reported as `malformed dial catalog reply` or `malformed dial in catalog reply` and is not printed as success.

### Known issues

- For OMP profiles, `open` does not refuse a hidden profile, and `profile.switch` does not check visibility. For a non-OMP harness, `open` refuses with the `unknown UltraTerm Profile` error, not `HiddenProfileError:`. `hide omp/NAME` is stored but changes nothing. Server fix is open work in UltraTerm, not in this release.
- `profiles hidden` and `profiles show` do not account for profiles hidden because their provider was removed. Server fix is open work in UltraTerm, not in this release.
- Some `provider.dials` content-rule messages and the busy refusal (`Dial configuration busy; retry`) are not documented in 3.14.

## [2.6.0] - 2026-10-11

Documents the profile visibility and usage dial commands that came with the UltraTerm 3.2 line and are unchanged in 3.2.10. The wire version stays 2; the commands are additive. A server that predates them rejects the command as unknown, and the client reports that plainly. UltraTerm 3.2.5 through 3.2.10 changed no other UTP command.

### Added

- `profiles.visibility` command (spec 3.13): `list`, `hide` and `show` with `harnessId` and `profile`. `hide` and `show` are a dry run unless `confirm:true`; ids are 1–64 lowercase letters, digits, `.`, `_` or `-`, not starting with `-`, `.` or `_`; at most 128 profiles can be hidden. Refusals: `profiles.visibility action must be list, hide or show`, `profiles.visibility hide requires harnessId and profile`, `profiles.visibility harness and harnessId disagree`, `HiddenProfileError: … is not a valid harness/profile id`, `at most 128 profiles can be hidden`, and `Profile visibility controls are disabled in an isolated mirror host`.
- `open` and `profile.switch` refuse a hidden profile with an error beginning `HiddenProfileError:` (spec 3.13).
- `provider.dials` command with the `list` and `upsert` actions (spec 3.14): the usage dial catalog and its revision, and a revision-checked save of one dial. Refusals: `expectedRevision is required; list the catalog first`, `Dial revision conflict; reload and retry`, `Invalid provider dial configuration`, `Unknown provider.dials action`, and `Provider dial controls are disabled in an isolated mirror host`.
- `utp profiles hidden`, `utp profiles hide|show HARNESS/PROFILE [--confirm]`, `utp dials list` and `utp dials enable|disable ID [--confirm]` in the reference client. Changes are a dry run unless `--confirm` is given; a dial toggle sends the whole dial back with only `enabled` changed and reports `DialRevisionConflictError` if the catalog changed in between.
- `diagnose` may list optional commands in a `capabilities` array (spec 9).

## [2.5.0] - 2026-10-10

Documents the protocol changes shipped in UltraTerm 3.2.4. The wire version stays 2; the new fields are additive. A server that predates 3.2.4 rejects `refit` as an unknown command and omits `receiptKnown`, which the client reports plainly.

### Added

- `refit` command: `{"cmd":"refit","slot":N}` asks the workspace window to re-measure, resize and redraw one terminal, or every attached terminal when `slot` is omitted. It repairs a blank or mis-sized pane and writes nothing to the session. A `slot` outside 1–32 is refused with `slot must be between 1 and 32`, an unattached slot with `no session on slot N` (a named slot is never widened to all terminals), and `id` with `refit takes slot, not id`. The reply is `{"ok":true,"refit":{"all":bool,"terminals":[{"slot":N,"id":"SESSION_UUID"}]},"delivery":"signalled; ..."}`: it signals the window, which applies the refit on its next frame, unconfirmed. Spec 3.11.
- `utp refit [--slot N]` prints one `refit requested` line per terminal, or says that no terminals are attached.
- `agent.send` is documented (spec 3.12): text of exactly one non-control character is delivered to a background agent as a literal keypress, so numbered and yes/no pickers that ignore pasted input receive `1` or `y`; longer text, and a single control character, is delivered as a bracketed paste.

### Changed

- A busy Claude Code terminal can receive `message` and `task.done`. The server finds the agent host on the active pane and then on every live pane of the terminal (at most 8; two different hosts are refused), and when no pane publishes one it falls back to the terminal's verified inbox registration. Otherwise the send fails with `has no live agent host` and nothing is queued. Spec 3.4.
- A refused native `message` or `task.done` replies with `receiptId` and `receiptKnown`. `receiptKnown:true` means the server holds that receipt; `false` means nothing was queued and no receipt exists. `utp message` and `utp task-done` now print `receiptId=` on stderr only after an accepted send, after a refusal with `receiptKnown:true`, and after a transport failure that may have reached the server; a refusal with `receiptKnown:false` says that nothing was queued and no receipt exists. Previously the id was printed before the request was sent, which sent callers to `utp receipt` for an `unknown receipt` after a refusal.
- A background worker (no terminal slot, identified by `fromId`) that sends a native `message` is refused with `WorkerSenderUnsupportedError` before any host lookup and nothing is queued; this was previously reported as `sender replaced`. A `noticeOnly` message from a worker is not refused.

## [2.4.0] - 2026-09-27

### Removed

- Removed the optional UltraCompact integration. `utp inspect` now prints plain terminal text; `--no-uc` remains a deprecated no-op. Legacy `utp savings` calls fail with a clear removal message instead of reading telemetry.

## [2.3.0] - 2026-09-26

The wire version stays 2; servers that predate these fields keep returning
`modelRead:false` and reject `waitUntil`, which the client reports plainly.

### Added

- Receipts say whether the recipient model read a note. A recorded receipt reports `modelRead`/`readAt` when the recipient model first responded after the recorded entry and `agentAcknowledged`/`acknowledgedAt` when it then produced output. `deliveryState` names every state (`recorded-awaiting-read`, `read`, `acknowledged`, …) and `guidance` says why a note is unread and what happens next.
- `message.receipt` waits accept `waitUntil`: `recorded` (default), `read` or `acknowledged`. `utp receipt ID --wait SECONDS --until read` waits for the model to read it and exits nonzero on timeout with the current state and reason.

## [2.2.1] - 2026-09-26

Client-only release; the wire version stays 2.

### Security

- `utp send` and `utp inspect` now honor `--id` when `--slot` is also given, as the spec's id precedence requires; previously the explicit session ID was silently dropped and the request went to whatever occupied the slot.
- `utp handoff` rejects a packet path containing control characters before sending anything. The path is typed into the worker PTY, and a CR or LF inside it would submit a truncated path that was never validated (for example `/tmp/evil` from `/tmp/evil\rx.md`).
- Text report items now enforce the documented rejection of commit identifiers and protected values: bare 7–40 character hex hashes, common credential shapes (GitHub, OpenAI-style, Slack, AWS access key, chat-bot tokens, JWTs, private-key headers) and `password=`/`token=` style assignments. Items containing Unicode line separators are rejected as multi-line. Previously only the literal word "commit" was caught, and these values were delivered to the hook.
- The report hook's directory must now be private as the spec requires: any group or other access is refused (`chmod 700`). Previously only group/world write access was refused, so a readable `0755` directory passed.

### Fixed

- Examples: `worker-complete.sh` no longer puts apostrophes inside `"${VAR:?...}"`. Under bash, including macOS `/bin/sh`, they mangled the messages and swallowed the `MANAGER_SESSION_ID` guard. `manager-delegate.sh` refuses a symlinked packet instead of `chmod`-ing the link's target.
- A failure reply carrying `committed:true` (spec 3.6: `close` removed the session but a later cleanup step failed) is now reported as committed, with advice not to retry. Handoff cleanup reports it as a close rather than as `cleanup failed`.
- Defer the `tempfile` and `uuid` imports to the commands that use them, cutting about 5 ms (8–12%) from every `utp` invocation.

## [2.2.0] - 2026-09-20

- Add read-only `diagnose` JSON diagnostics and `utp --version` (`2.2.0`); wire version remains 2.
- Bound client reply memory and exchange duration; cleanly reject timeout, refusal, disconnect, truncated, oversized, malformed and invalid inspect replies.
- Never replay requests automatically; report unknown mutation outcomes after sending begins and document read-only reconciliation.
- Merge newer vendored harness-scoped profiles, identity checks, native-identity manager registration and receipt-aware messaging into the canonical executable client.
- Require `utp register-manager --from-id WORKER_SESSION_ID --expected-id MANAGER_SESSION_ID` and `utp task-done --from-id WORKER_SESSION_ID`; an explicit `task-done --to MANAGER_SLOT` additionally requires `--expected-id`. Session IDs come from `list` and are never inferred from a slot.
- Pin every worker-to-manager route to both native agent conversations. Registrations persist across an app restart and across slot renumbering, a replaced terminal never inherits an older route, and a stale or unauthenticated conversation is rejected instead of redirected.
- Deliver `task.done` and addressed `message` payloads through the native conversation inbox only; nothing is typed into a manager PTY, and no receipt is presented as host acceptance, agent acknowledgment or proof of a model read.
- Version the local manager route store as format 3 while the wire version stays 2; legacy slot-only records are not migrated.
- Make confirmed handoff wait for the receiving session, register that exact worker session against the manager session ID from `list`, and pin packet submission to the captured worker session ID; a pre-submit failure (readiness timeout, registration error, cancellation) closes only the pane that handoff opened, identity-bound to the session ID it opened, while an attempted-but-unconfirmed submission keeps the worker and prints its session ID for the operator to reconcile.
- Add isolated Unix-socket Python CLI transport tests plus deterministic registration, compatibility and secure-failure CLI tests.


## [2.1.0] - 2026-08-30

### Added

- `utp report --kind file|image --file PATH` delivers one regular, non-empty file up to 45 MiB by resolved path; `--summary` is an optional caption of at most 1024 characters.
- `utp redact --route ROUTE --project NAME --message-id N [...] --reason TEXT --user-authorized` deletes the bot's own prior messages by explicit ID only, with one audit record for every call.

### Changed

- Text reports now use repeatable `--new`, `--changed`, and `--fixed` items rendered as separate scannable sections. Paragraph summaries and recipient-irrelevant technical workflow details are rejected.
- The public reference client now matches the installed UltraTerm client, including automatic caller-slot discovery, provider-neutral profile routing, and the built-in `Auto` profile label.
- Public report-hook examples and fixtures use neutral route aliases.

### Security

- Redaction accepts only 1–20 explicit positive message IDs and deletes only the hook provider's own prior messages.
- Report validation rejects protected values and technical workflow details before a user-owned hook receives the payload.

## [2.0.0] - 2026-08-24

### Added

- Identity-bound `profile.switch` handoff with startup rollback and distinct successful, restored, and unrecoverable UI outcomes.
- Universal `utp handoff` composition for same-slot replacement or a new managed worker.
- Private, symlink-safe, current-user-owned handoff packets under `/tmp`, capped at 16 KiB.
- Many-workers-to-one-manager orchestration through persistent manager registration.
- Universal `utp report --route` aliases for chat bots, groups, local inboxes, and generic user-owned hooks.

### Changed
- Existing universal profile list/create/remove commands are now part of the normative v2 specification.

- Confirmed `close` and in-place `switch-profile`/`handoff` now require the session ID printed by a fresh dry run.
- Confirmed `open` attaches the assigned slot and pane; confirmed `close` removes that exact slot and pane.
- Profile handoff attaches the replacement before its startup health check and repaints every live pane through the normal theme appearance-refresh path.
- Terminal orchestration and external reporting require explicit user authorization. Agents may suggest capacity-aware orchestration but cannot confirm it autonomously.

### Security

- Stale or reused slot identities are rejected under the mutation lock without changing the current session.
- Handoff packets reject paths outside `/tmp`, symlinks, non-user ownership, non-private permissions, empty content, and oversized content.
- Report routes are aliases; chat IDs, provider tokens, authentication, and delivery logic remain in a user-owned local hook.

## [1.0.0] - 2026-08-24

### Added

- JSON Lines protocol over the same-user Unix socket at `~/.ultraterm/utp.sock`.
- `list`, `inspect`, `send`, addressed `message`, guarded `open`/`close`, `register-manager`, and `task-done`.
- Persistent worker-to-manager mappings and a stdlib-only Python reference client.

### Security

- Directory mode `0700`, socket mode `0600`, no TCP listener, and bounded request/message/output buffers.
