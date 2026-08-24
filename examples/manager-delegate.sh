#!/bin/sh
set -eu

MANAGER_SLOT=${MANAGER_SLOT:-1}
WORKER_SLOT=${WORKER_SLOT:-2}
PROFILE=${PROFILE:-quality}
PACKET=${1:-/tmp/ultraterm-handoff.md}

test -f "$PACKET"
chmod 600 "$PACKET"

# Safe suggestion only. After explicit user approval, repeat the printed plan
# with --confirm --user-authorized and its exact --expected-id.
utp handoff \
  --slot "$WORKER_SLOT" \
  --profile "$PROFILE" \
  --packet "$PACKET" \
  --manager-slot "$MANAGER_SLOT"
