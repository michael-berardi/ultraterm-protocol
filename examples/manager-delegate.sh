#!/bin/sh
set -eu

MANAGER_SLOT=${MANAGER_SLOT:-1}
WORKER_SLOT=${WORKER_SLOT:-2}
PROFILE=${PROFILE:-quality}
PACKET=${1:-/tmp/ultraterm-handoff.md}

test -f "$PACKET"
chmod 600 "$PACKET"

# Safe suggestion only. After explicit user approval, repeat the printed plan
# with --confirm --user-authorized and its exact --expected-id. A confirmed
# handoff waits for the receiver, then registers that exact worker session ID
# against the manager session ID it read from `utp list`; registrations and
# completions are never typed into a PTY.
utp handoff \
  --slot "$WORKER_SLOT" \
  --profile "$PROFILE" \
  --packet "$PACKET" \
  --manager-slot "$MANAGER_SLOT"
