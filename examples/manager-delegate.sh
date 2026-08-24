#!/bin/sh
set -eu

MANAGER_SLOT=${MANAGER_SLOT:-1}
WORKER_SLOT=${WORKER_SLOT:-2}
TASK=${1:-"Run the focused regression suite and report the exact totals."}

# The message is an addressed visual cue; send types the task into the worker PTY.
utp message --from "$MANAGER_SLOT" --to "$WORKER_SLOT" "$TASK"
utp send --slot "$WORKER_SLOT" "$TASK"
