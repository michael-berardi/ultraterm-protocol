# Security policy

## Supported versions

Security fixes land on `main` and ship in the next release. Only the latest
release of the UTP reference client is supported.

## Reporting a vulnerability

Please report vulnerabilities privately through
[GitHub private vulnerability reporting](https://github.com/michael-berardi/ultraterm-protocol/security/advisories/new).
Do not open a public issue for an undisclosed vulnerability.

Include the affected version, your operating system, reproduction steps and
the impact you observed. Leave out credentials, personal data and private
files; a minimal synthetic reproduction is enough.

You can expect an acknowledgement within 7 days. Reporters are credited in
the release notes if they want to be.

## Scope

UTP is a same-user local protocol over a `0600` Unix socket with no TCP
listener. In scope: ways for another local user to reach the socket, identity
checks that can be bypassed so a destructive command hits the wrong session,
report hooks that leak content to an unintended destination, and client
parsing flaws. Attacks that assume a compromised account of the same user are
out of scope.
