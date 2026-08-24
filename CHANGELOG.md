# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.0.0] - 2026-08-24

### Added

- UltraTerm Terminal Protocol v1 using JSON Lines over the same-user Unix socket at `~/.ultraterm/utp.sock`.
- `list`, `inspect`, `send`, and addressed `message` commands for persistent terminal discovery, output inspection, PTY input, and local coordination.
- Guarded `open` and `close` commands with dry-run responses by default and explicit confirmation before session changes.
- `register-manager` and `task-done` commands for worker-to-manager completion routing.
- Persistent worker-to-manager mappings stored in `~/.ultraterm/manager-map.json` across app restarts.
- Stdlib-only Python reference client plus manager-delegation and worker-completion shell examples.

### Security

- Same-user local transport only: directory mode `0700`, socket mode `0600`, and no TCP listener.
- Bounded request, message, inspection, and PTY-output buffers.
