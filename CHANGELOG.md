# Changelog

All notable changes are documented here. This project follows Keep a Changelog and Semantic Versioning.

## [Unreleased]

### 2.2.0 candidate

- Add read-only `diagnose` JSON diagnostics and `utp --version` (`2.2.0`); wire version remains 2.
- Bound client reply memory and exchange duration; cleanly reject timeout, refusal, disconnect, truncated, oversized, malformed and invalid inspect replies.
- Never replay requests automatically; report unknown mutation outcomes after sending begins and document read-only reconciliation.
- Handle unavailable/nonexecutable optional UC codecs cleanly, preserving explicit `--no-uc` behavior.
- `utp savings` exits nonzero with the codec's error when `uc telemetry` fails; it previously printed nothing and exited 0.
- Merge newer vendored harness-scoped profiles, identity checks, native-identity manager registration and receipt-aware messaging into the canonical executable client.
- Require `utp register-manager --from-id WORKER_SESSION_ID --expected-id MANAGER_SESSION_ID` and `utp task-done --from-id WORKER_SESSION_ID`; an explicit `task-done --to MANAGER_SLOT` additionally requires `--expected-id`. Session IDs come from `list` and are never inferred from a slot.
- Pin every worker-to-manager route to both native agent conversations. Registrations persist across an app restart and across slot renumbering, a replaced terminal never inherits an older route, and a stale or unauthenticated conversation is rejected instead of redirected.
- Deliver `task.done` and addressed `message` payloads through the native conversation inbox only; nothing is typed into a manager PTY, and no receipt is presented as host acceptance, agent acknowledgment or proof of a model read.
- Version the local manager route store as format 3 while the wire version stays 2; legacy slot-only records are not migrated.
- Make confirmed handoff wait for the receiving session, register that exact worker session against the manager session ID from `list`, and pin packet submission to the captured worker session ID; a pre-submit failure (readiness timeout, registration error, cancellation) closes only the pane that handoff opened, identity-bound to the session ID it opened, while an attempted-but-unconfirmed submission keeps the worker and prints its session ID for the operator to reconcile.
- `utp send` and `utp inspect` now honor `--id` when `--slot` is also given, as the spec's id precedence requires; previously the explicit session ID was silently dropped and the request went to whatever occupied the slot.
- `utp handoff` rejects a packet path containing control characters before sending anything. The path is typed into the worker PTY, and a CR or LF inside it would submit a truncated path that was never validated (for example `/tmp/evil` from `/tmp/evil\rx.md`).
- Text report items now enforce the documented rejection of commit identifiers and protected values: bare 7–40 character hex hashes, common credential shapes (GitHub, OpenAI-style, Slack, AWS access key, chat-bot tokens, JWTs, private-key headers) and `password=`/`token=` style assignments. Items containing Unicode line separators are rejected as multi-line. Previously only the literal word "commit" was caught, and these values were delivered to the hook.
- Examples: `worker-complete.sh` no longer puts apostrophes inside `"${VAR:?...}"`. Under bash, including macOS `/bin/sh`, they mangled the messages and swallowed the `MANAGER_SESSION_ID` guard. `manager-delegate.sh` refuses a symlinked packet instead of `chmod`-ing the link's target.
- A failure reply carrying `committed:true` (spec 3.6: `close` removed the session but a later cleanup step failed) is now reported as committed, with advice not to retry. Handoff cleanup reports it as a close rather than as `cleanup failed`.
- Defer the `tempfile` and `uuid` imports to the commands that use them, cutting about 5 ms (8–12%) from every `utp` invocation.
- Add isolated Unix-socket Python CLI transport tests plus deterministic registration, compatibility and secure-failure CLI tests. No release, tag or publication yet.


## [2.1.0] - 2026-08-30

### Added

- `utp report --kind file|image --file PATH` delivers one regular, non-empty file up to 45 MiB by resolved path; `--summary` is an optional caption of at most 1024 characters.
- `utp redact --route ROUTE --project NAME --message-id N [...] --reason TEXT --user-authorized` deletes the bot's own prior messages by explicit ID only, with one audit record for every call.
- `utp savings [--rate DOLLARS_PER_MILLION]` summarizes local UltraCompact token savings for the day, 7 days, 30 days, and all time.

### Changed

- Text reports now use repeatable `--new`, `--changed`, and `--fixed` items rendered as separate scannable sections. Paragraph summaries and recipient-irrelevant technical workflow details are rejected.
- `utp inspect` now emits model-readable UltraCompact output by default; `--no-uc` preserves plain PTY history for standalone clients and debugging.
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
