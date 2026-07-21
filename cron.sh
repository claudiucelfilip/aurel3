#!/bin/bash
# Aurel3 runtime wrapper.
# Entry-scan interpretation runs in the OpenClaw agent-turn, not via this wrapper.
# Suggested cron entries for the remaining commands:
# 30 10,14,18,20 * * 1-5   bash /root/aurel3/cron.sh watchlist_review
# 0 21 * * 1-5        bash /root/aurel3/cron.sh review_signals
# 0 9 * * 0           bash /root/aurel3/cron.sh review_summary

set -uo pipefail

cd /root/aurel3
LOGFILE="/root/aurel3/data/runtime.log"
COMMAND="${1:-signal_scan}"
LOCKFILE="/root/aurel3/data/${COMMAND}.lock"

exec 9>"$LOCKFILE"
if ! flock -n 9; then
    echo "$(date -u '+%Y-%m-%dT%H:%M:%SZ') skipped ${COMMAND}: another run is still active" >> "$LOGFILE"
    exit 0
fi

python3 run.py "$COMMAND" >> "$LOGFILE" 2>&1
EXIT_CODE=$?

if [ "$EXIT_CODE" -ne 0 ]; then
    # Pipeline failure → ping Slack so a stalled cron doesn't go unnoticed
    # for days (cf. Gemini quota exhaustion 2026-04-03 → 2026-04-08).
    python3 run.py notify_failure "$COMMAND" "$EXIT_CODE" >> "$LOGFILE" 2>&1 || true
fi

exit "$EXIT_CODE"
