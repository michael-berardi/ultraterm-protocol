#!/bin/sh
set -eu

: "${ULTRATERM_SLOT:?Set ULTRATERM_SLOT to this worker terminal slot}"
MANAGER_SLOT=${MANAGER_SLOT:-1}
SUMMARY=${1:-"Focused regression suite passed."}

# Registration persists, so later completions need only task-done.
utp register-manager --slot "$MANAGER_SLOT"
utp task-done --summary "$SUMMARY"
