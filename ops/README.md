# Aurel3 ops

## Performance dashboard

A read-only FastAPI view of `data/` — the managed-exit scoreboard, a hypothetical
equity curve, the recommendation log, and the per-theme scorecard. It never
writes to `data/`; the signal cycle owns those files.

- Code: `dashboard/app.py` (web layer) and `dashboard/metrics.py` (aggregation).
- Listens on `127.0.0.1:8082`, published by the existing cloudflared tunnel at
  <https://aurel3.clawdiu.org>. The tunnel ingress is already configured — do
  not edit `~/.cloudflared/config.yml`.

### Install on Dumbo

Dependencies come from the host python 3.9 that cron already uses:

```
python3 -m pip install --user fastapi uvicorn jinja2
```

Then install and start the agent:

```
cp /Users/claudiu/vps-root/aurel3/ops/org.clawdiu.aurel3-dashboard.plist ~/Library/LaunchAgents/
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/org.clawdiu.aurel3-dashboard.plist
```

Reload after a code change:

```
launchctl kickstart -k gui/$(id -u)/org.clawdiu.aurel3-dashboard
```

Logs go to `~/Library/Logs/aurel3-dashboard.log`.

### Verify

```
curl -sf http://127.0.0.1:8082/healthz
curl -sf https://aurel3.clawdiu.org | grep -o 'Aurel3 — Signal Performance'
```

### Caching

Price lookups are cached 15 minutes and the whole page payload 10 minutes, so a
page load does not re-walk yfinance. `/?refresh=1` forces a rebuild.
