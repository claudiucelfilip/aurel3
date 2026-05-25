# WORKTREE_HANDOFF.md

owner: Claw
created_utc: 2026-05-25T09:18:59Z
repo: /root/aurel3
service: Aurel3 signal engine
purpose: Uncommitted Aurel3 experiments and runtime fixes were found during the 2026-05-25 audit. Treat as unreviewed until classified; do not silently discard or promote.

## Production Impact

active_in_runtime: yes
money_or_trading_adjacent: yes

## Changed Files

Run `git status --short` in this repo for the current list. This handoff marks the dirty state as known, not approved.

## Tests / Evidence

- 2026-05-25 read-only audit identified dirty worktree state.
- No cleanup, stash, discard, deploy, or service restart was performed by this handoff.

## Recommended Action

Classify each change as ship / keep-testing / stash / discard / ask-human. Trading-adjacent files require human approval before discard, deploy, or restart.

## Next Check

due_utc: next Claw heartbeat or weekly ops review
owner: Claw / Gatekeeper
