#!/bin/sh
# heimdallr resume wrapper.
#
# usage: resume_wrapper.sh <db_path> <session_id> <agent> <agent_argv...>
#
# Records this shell's PID in heimdallr's spawned_pids table BEFORE exec.
# POSIX preserves the PID across exec, so the recorded PID *is* the agent's
# PID after the exec line. The wrapper then disappears, the agent runs in
# our shell, and heimdallr's pid_tracker can identify the running session.
#
# If sqlite3 isn't available the INSERT silently fails and we still exec.
# `hmd doctor` reports missing sqlite3 so the user knows tracking is degraded.

set -e

DB="$1"
SID="$2"
AGENT="$3"
shift 3 || exit 1

if command -v sqlite3 > /dev/null 2>&1; then
    sqlite3 "$DB" \
        "INSERT OR REPLACE INTO spawned_pids (pid, session_id, agent, started_at) \
         VALUES ($$, '$SID', '$AGENT', strftime('%s','now'));" \
        > /dev/null 2>&1 || true
fi

exec "$@"
