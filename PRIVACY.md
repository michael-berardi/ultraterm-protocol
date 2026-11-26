# Privacy details

This document expands the short [Privacy section](README.md#privacy). It describes the reference client in this repository; the UltraTerm server and any report hook are separate software with their own storage.

The UTP client has no telemetry, analytics, crash reporting, accounts or install identifiers. Commands talk only to the local UltraTerm socket. The only network traffic is the update check and the update download described below.

## Local-only protocol facts

- Each command connects to the same-user Unix socket at `~/.ultraterm/utp.sock`, or prints help/errors without connecting. The control transport is `AF_UNIX` only: no TCP listener and no remote control endpoint.
- The client may ask the local `tmux` binary for the session name when `TMUX_PANE` is set, solely to discover the caller slot. It sends no terminal content in that request.
- `utp report` and `utp redact` require `--user-authorized`. They invoke only a user-owned executable at `~/.ultraterm/report-hook` (or `UTP_REPORT_HOOK`) and pass a JSON payload on standard input. The client does not choose a destination or store hook credentials. If the hook delivers to a chat service, that service receives what you authorized; text reports reject credential-shaped values before the hook runs.
- Native messages you send through UltraTerm go to agent hosts you configured; their model providers receive the prompts you send. UTP neither selects a provider nor forwards data to one by itself.
- Destructive commands are dry runs until confirmed with a fresh session ID. Replies are bounded to 1 MiB, exchanges normally end after 10 seconds, and the client never retries a request automatically. After a failed mutation it asks you to reconcile with read-only queries.

## Update check and download

- **Update check.** At most once per 24 hours, and only when stdout and stderr are terminals, one anonymous HTTPS GET reads this repository's public latest-release record from `api.github.com` with the fixed User-Agent `utp-update-check` and a 4-second timeout. It carries no version, identifier, machine, session, terminal or usage data. It is skipped when `CI` or `CLAUDECODE` is set, with `UTP_NO_UPDATE_CHECK=1`, and after `utp update --checks off`. `utp update` and `utp update --check` run the same request when you ask for it.
- **Update download.** Only when you run `utp update`, or after you turn on automatic updates (off by default), the client downloads the release's `utp` and `SHA256SUMS` files from `raw.githubusercontent.com`. It installs only when the SHA-256 and the version inside the file match.
- **What GitHub sees.** As with any web request, GitHub sees the requesting IP address. Nothing else leaves the machine.

See [docs/updates.md](docs/updates.md) for the commands and the install safety rules.

## Dependencies and installation

- The reference client is one Python 3 script using only the standard library. There are no runtime packages, manifests, plug-ins or third-party imports; it is tested with Python 3.15.
- The README's single-file install uses `curl` to fetch a URL pinned to release 2.9.0 into `./utp`, then verifies its SHA-256 before you run it. This is the only network fetch in the documented install path; the fetched bytes are the checked client and no installer identifier is retained.
- A source install uses `git clone`, which writes a checkout containing the client, protocol specifications, documentation and tests. Run the client from that checkout; no symlink or PATH change is required. In a checkout, `utp update` runs `git pull --ff-only`. UltraTerm may also manage its own copy at `~/.ultraterm/bin/utp`, which updates with UltraTerm.
- README rendering loads no remote badges or scripts. Local checks use synthetic fixtures, disposable sockets and a local release server; they do not require a running UltraTerm app or the network.

## Local writes

The reference client writes only the update files listed first below; it keeps no command history, terminal output, tokens or telemetry. Other components can write as listed after them. Paths under `~` are relative to the current user's home directory. `CACHE` is `~/Library/Caches` on macOS and `$XDG_CACHE_HOME` (default `~/.cache`) elsewhere.

| Writer | Path | Contents | Lifetime / bound | Cleanup | Deletion |
|---|---|---|---|---|---|
| Reference client: update state | `CACHE/utp/update.json` (file `0600`, directory `0700`) | Check time, latest stable version or the failure cause, your skip, automatic-install and check choices, when the notice was last shown and the last automatic-install failure. | One small file, replaced atomically on each write; kept until you delete it. | Each write replaces the previous copy; no history is kept. | `utp update --auto off` deletes it (it keeps only a `--checks off` choice, if you made one). |
| Reference client: automatic-install log | `CACHE/utp/update.log` (file `0600`) | One line per automatic install: time, version and the failure cause, if any. | Written only with automatic updates on; trimmed to the newest 256 KB. | The oldest lines are dropped at the bound. | `utp update --auto off` deletes it. |
| Reference client: rollback copy | `<client>.previous` beside the client | The client replaced by the last `utp update`. | Deleted after the new client's first successful run, or after seven days. | Automatic. | `utp update --rollback` restores it; `rm utp.previous` deletes it. |
| Reference client: update staging | `utp-update-*` directory beside the client | The verified download, staged for the atomic swap. | Exists only while `utp update` installs. | Removed on success and on failure. | Nothing to delete. |
| README single-file installer | `./utp` in the working directory | Exact client bytes downloaded from the pinned release and checked against the README SHA-256. | Retained until you replace or delete it. | `utp update` replaces it with a verified newer release. | `rm utp` from that directory. |
| Source install | `ultraterm-protocol/` checkout | Repository source, docs, protocol specs and tests. | Retained until you update or delete the checkout; Git tracks local changes. | `utp update` runs `git pull --ff-only`; tracked files are never rewritten by the client. | Remove the checkout only after saving any local work. |
| UltraTerm server (separate app) | `~/.ultraterm/manager-map.json` | Format 3 worker-to-manager identity routes. The client never writes or reads this file directly. | Persists across app restarts and slot renumbering; server-managed, with no client-set expiry. An unreadable or invalid file is treated as empty, not migrated. | Re-registering a worker replaces that worker's previous route; the server owns any retention policy. | Stop UltraTerm, delete the file, then explicitly re-register routes you still need. |
| Operator handoff packet | `/tmp/PACKET` or the platform temp directory | Handoff Markdown you create, at most 16 KiB. The client only reads, validates and passes its path to the worker. | Retained until you remove it or the operating system cleans temp storage; the client sets no timer and never deletes it. | Keep mode `0600` and remove it when the handoff is no longer needed. | `rm /tmp/PACKET` (or your chosen path). |
| Optional user report hook | `~/.ultraterm/report-hook` / `UTP_REPORT_HOOK`, plus any files its code writes | Hook program you install; any message audit, delivery logs or saved credentials are entirely hook-owned. | Retention is set by the hook owner, never by UTP; the client holds none of these values. | Review the hook's own log rotation and retention settings. | Delete hook-installed files and logs you own after you stop using the route. |
| Example shell script | The `PACKET` path you pass to `examples/manager-delegate.sh` | Permission bits only: the example refuses symlinks and non-regular files, then applies `chmod 600`. No file content or log is written. | Mode change lasts until you change it again. | Run the example only on a packet you own; it never creates a file. | `chmod` the mode back if desired, then delete the packet. |
| Local test suite (development only) | Temporary directories under the platform temp directory | Synthetic client, hook, socket, packet and release fixtures. | Bounded to one test run; `TemporaryDirectory` contexts and `addCleanup` hooks remove them on exit. | No manual step; cleanup is automatic even when a test fails. | Automatic at test exit. |

## Removing local data

Run `utp update --auto off` to delete the update state and log, then delete the client file and `utp.previous`, if present. To remove data from the other components, stop UltraTerm and delete `~/.ultraterm/manager-map.json` only if you no longer need registered routes, delete your `/tmp` handoff packets, and delete any audit or delivery logs your own report hook created. Native messages, receipts and terminal history belong to UltraTerm and to the configured agent hosts, not to this client.
