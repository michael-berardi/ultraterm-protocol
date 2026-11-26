# Privacy details

This document expands the short [Privacy section](README.md#privacy). It describes the reference client in this repository; the UltraTerm server and any report hook are separate software with their own storage.

## Local-only protocol facts

- Each command connects to the same-user Unix socket at `~/.ultraterm/utp.sock`, or prints help/errors without connecting. The client uses `AF_UNIX` only: no TCP listener, no DNS, no HTTP, no telemetry, no analytics, no crash reporting and no install ID.
- No update check runs, so there is nothing to opt out of; no update prompt is implemented. Updates are manual.
- The client may ask the local `tmux` binary for the session name when `TMUX_PANE` is set, solely to discover the caller slot. It sends no terminal content in that request.
- `utp report` and `utp redact` require `--user-authorized`. They invoke only a user-owned executable at `~/.ultraterm/report-hook` (or `UTP_REPORT_HOOK`) and pass a JSON payload on standard input. The client does not choose a destination or store hook credentials. If the hook delivers to a chat service, that service receives what you authorized; text reports reject credential-shaped values before the hook runs.
- Native messages you send through UltraTerm go to agent hosts you configured; their model providers receive the prompts you send. UTP neither selects a provider nor forwards data to one by itself.
- Destructive commands are dry runs until confirmed with a fresh session ID. Replies are bounded to 1 MiB, exchanges normally end after 10 seconds, and the client never retries a request automatically. After a failed mutation it asks you to reconcile with read-only queries.

## Dependencies and installation

- The reference client is one Python 3 script using only the standard library. There are no runtime packages, manifests, plug-ins or third-party imports; it is tested with Python 3.15.
- The README's single-file install uses `curl` to fetch a URL pinned to release 2.8.5 into `./utp`, then verifies its SHA-256 before you run it. This is the only network fetch in the single-file install path (a source install fetches the repository with `git clone` instead); the fetched bytes are the checked client and no installer identifier is retained.
- A source install uses `git clone`, which writes a checkout containing the client, protocol specifications, documentation and tests. Run the client from that checkout; no symlink or PATH change is required. UltraTerm may also manage its own copy at `~/.ultraterm/bin/utp`.
- README rendering loads no remote badges or scripts. Local checks use synthetic fixtures and disposable sockets; they do not require a running UltraTerm app.

## Local writes

The reference client itself writes no files and creates no logs, cache, history, tokens or state files. Other components can write as listed below. Paths under `~` are relative to the current user's home directory.

| Writer | Path | Contents | Lifetime / bound | Cleanup | Deletion |
|---|---|---|---|---|---|
| Reference client at runtime | None | No file, log, cache, history, token or state is written; output goes to stdout/stderr only. | No retention because nothing is stored. | Nothing to clean up. | Nothing to delete. |
| README single-file installer | `./utp` in the working directory | Exact client bytes downloaded from the pinned release and checked against the README SHA-256. | Retained until you replace or delete it; the verified download is the replacement path. No automatic cleanup. | Re-download and re-verify to replace an older copy. | `rm utp` from that directory. |
| Source install | `ultraterm-protocol/` checkout | Repository source, docs, protocol specs and tests. | Retained until you update or delete the checkout; Git tracks local changes. | Use Git to review or update the checkout; no automatic cleanup. | Remove the checkout only after saving any local work. |
| UltraTerm server (separate app) | `~/.ultraterm/manager-map.json` | Format 3 worker-to-manager identity routes. The client never writes or reads this file directly. | Persists across app restarts and slot renumbering; server-managed, with no client-set expiry. An unreadable or invalid file is treated as empty, not migrated. | Re-registering a worker replaces that worker's previous route; the server owns any retention policy. | Stop UltraTerm, delete the file, then explicitly re-register routes you still need. |
| Operator handoff packet | `/tmp/PACKET` or the platform temp directory | Handoff Markdown you create, at most 16 KiB. The client only reads, validates and passes its path to the worker. | Retained until you remove it or the operating system cleans temp storage; the client sets no timer and never deletes it. | Keep mode `0600` and remove it when the handoff is no longer needed. | `rm /tmp/PACKET` (or your chosen path). |
| Optional user report hook | `~/.ultraterm/report-hook` / `UTP_REPORT_HOOK`, plus any files its code writes | Hook program you install; any message audit, delivery logs or saved credentials are entirely hook-owned. | Retention is set by the hook owner, never by UTP; the client holds none of these values. | Review the hook's own log rotation and retention settings. | Delete hook-installed files and logs you own after you stop using the route. |
| Example shell script | The `PACKET` path you pass to `examples/manager-delegate.sh` | Permission bits only: the example refuses symlinks and non-regular files, then applies `chmod 600`. No file content or log is written. | Mode change lasts until you change it again. | Run the example only on a packet you own; it never creates a file. | `chmod` the mode back if desired, then delete the packet. |
| Local test suite (development only) | Temporary directories under the platform temp directory | Synthetic client, hook, socket and packet fixtures. | Bounded to one test run; `TemporaryDirectory` contexts and `addCleanup` hooks remove them on exit. | No manual step; cleanup is automatic even when a test fails. | Automatic at test exit. |

## Removing local data

The UTP client leaves no state to erase. To remove data from the other components, stop UltraTerm and delete `~/.ultraterm/manager-map.json` only if you no longer need registered routes, delete your `/tmp` handoff packets, and delete any audit or delivery logs your own report hook created. Native messages, receipts and terminal history belong to UltraTerm and to the configured agent hosts, not to this client.
