# Privacy

The UTP client has no telemetry, accounts or identifiers. It talks to the local UltraTerm
socket and, for updates only, to GitHub.

- **Update check.** At most once per 24 hours, and only when stdout and stderr are terminals,
  one anonymous HTTPS GET reads this repository's public latest-release record from
  `api.github.com` with the fixed User-Agent `utp-update-check`. It carries no version,
  identifier, machine, session, terminal or usage data. It is skipped when `CI` or
  `CLAUDECODE` is set, with `UTP_NO_UPDATE_CHECK=1`, and after `utp update --checks off`.
- **Update download.** Only when you run `utp update`, or after you turn on automatic
  updates, the client downloads the release's `utp` and `SHA256SUMS` files from
  `raw.githubusercontent.com`.
- **Local state.** One `0600` file, `utp/update.json` in the platform cache directory, holds
  the check time, the latest version or the failure cause, your skip, automatic-install and
  check choices, and when the notice was last shown. Automatic installs log to `update.log`
  beside it (at most 256 KB). `utp update --auto off` deletes both.

As with any web request, GitHub sees the requesting IP address.
