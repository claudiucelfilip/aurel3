#!/bin/bash
# Nightly snapshot of Aurel3 state (data/). The learning corpus — watchlist,
# trade history, reviews — lives only on Dumbo's disk, so keep rotating local
# archives to survive corruption or accidental deletion.
set -euo pipefail

REPO="/root/aurel3"
DEST="/root/aurel3-backups"
STAMP=$(date -u '+%Y%m%d')

mkdir -p "$DEST"
tar -czf "$DEST/data-$STAMP.tgz" -C "$REPO" data

# Keep the newest 14 snapshots.
ls -1t "$DEST"/data-*.tgz 2>/dev/null | tail -n +15 | xargs rm -f
