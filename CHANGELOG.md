# Changelog

All notable changes are documented here. This project follows Keep a Changelog and Semantic Versioning.

## [Unreleased]

### Added

- `utp report --kind file|image --file PATH` delivers one regular, non-empty file up to 45 MiB by resolved path; `--summary` is an optional caption of at most 1024 characters.
- `utp redact --route ROUTE --project NAME --message-id N [...] --reason TEXT --user-authorized` deletes the bot's own prior messages by explicit ID only (1-20 positive IDs per call, deduplicated and sorted), with a fail-open audit entry written for every call.

### Changed

- Text reports now use repeatable `--new`, `--changed`, and `--fixed` items rendered as separate scannable sections. Paragraph summaries, verification chatter, deployment mechanics, commit identifiers, and rollback instructions are rejected as recipient-irrelevant noise.
- The reference client now matches the installed UltraTerm client, including
  provider-neutral profile routing and automatic caller-slot discovery inside
  UltraTerm tmux sessions.
- Public report-hook examples and fixtures use neutral route aliases.

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
