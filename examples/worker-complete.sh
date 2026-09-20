#!/bin/sh
set -eu

: "${ULTRATERM_SLOT:?Set ULTRATERM_SLOT to this worker terminal slot}"
MANAGER_SLOT=${MANAGER_SLOT:-1}
SUMMARY=${1:-"Focused regression suite passed."}

# Session IDs, never slot numbers, identify the sessions. Read both from
# `utp list` first: the worker's own ID and the manager's current ID.
: "${WORKER_SESSION_ID:?Set WORKER_SESSION_ID to this worker's session ID from utp list}"
: "${MANAGER_SESSION_ID:?Set MANAGER_SESSION_ID to the manager's session ID from utp list}"

# Registration pins both native conversations and persists, so later
# completions need only task-done. Completions go to the manager's native
# conversation inbox; they are never typed into a manager PTY.
utp register-manager \
  --slot "$MANAGER_SLOT" \
  --from-id "$WORKER_SESSION_ID" \
  --expected-id "$MANAGER_SESSION_ID"
utp task-done --from-id "$WORKER_SESSION_ID" --summary "$SUMMARY"
