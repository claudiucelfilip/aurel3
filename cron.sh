#!/bin/bash
# Aurel3 runtime wrapper.
# Suggested cron entries:
# 30 9,13,17 * * 1-5   bash /root/aurel3/cron.sh openclaw_cycle
# 30 10,14,18,20 * * 1-5   bash /root/aurel3/cron.sh watchlist_review
# 0 21 * * 1-5        bash /root/aurel3/cron.sh review_signals
# 0 9 * * 0           bash /root/aurel3/cron.sh review_summary

set -euo pipefail

cd /root/aurel3
LOGFILE="/root/aurel3/data/runtime.log"
COMMAND="${1:-signal_scan}"

python3 run.py "$COMMAND" >> "$LOGFILE" 2>&1
