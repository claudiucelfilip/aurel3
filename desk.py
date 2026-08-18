"""Manual trading desk — broker-agnostic order flow with a human at the keys.

Any strategy proposes orders (the DCA core, aurel3 signals, aurel2 once it
leaves Alpaca); the desk notifies the human, nags until the fill is confirmed,
and keeps the ledger, holdings, tax-lot ages, and deviations. No broker API —
execution is manual (Tradeville today), so the desk is reusable across
brokers unchanged. See DESK.md for the producer contract.
"""

from __future__ import annotations

import json
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path

from state import make_id, utc_now_iso, _load_json, _save_json

DESK_DIR = Path(__file__).parent / "data" / "desk"
ORDERS_PATH = DESK_DIR / "orders.json"
LEDGER_PATH = DESK_DIR / "ledger.jsonl"
STATE_PATH = DESK_DIR / "state.json"
INBOX_DIR = DESK_DIR / "inbox"

ORDER_EXPIRY_DAYS = 10
NAG_INTERVAL_HOURS = 24
LONG_TERM_LOT_DAYS = 365  # Romanian withholding drops 6% -> 3% past one year


# ---------------------------------------------------------------- storage

def load_orders() -> list[dict]:
    return _load_json(ORDERS_PATH)


def save_orders(orders: list[dict]) -> None:
    _save_json(ORDERS_PATH, orders)


def load_desk_state() -> dict:
    if not STATE_PATH.exists():
        return {}
    with open(STATE_PATH) as f:
        return json.load(f)


def save_desk_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(STATE_PATH, "w") as f:
        json.dump(state, f, indent=2)


def append_ledger(entry: dict) -> None:
    LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(LEDGER_PATH, "a") as f:
        f.write(json.dumps(entry) + "\n")


def load_ledger() -> list[dict]:
    if not LEDGER_PATH.exists():
        return []
    with open(LEDGER_PATH) as f:
        return [json.loads(line) for line in f if line.strip()]


# ---------------------------------------------------------------- orders

REQUIRED_ORDER_FIELDS = ("source", "action", "symbol")


def validate_proposal(fields: dict) -> list[str]:
    errors = [f"missing field: {k}" for k in REQUIRED_ORDER_FIELDS if not fields.get(k)]
    if fields.get("action") not in ("buy", "sell"):
        errors.append("action must be buy or sell")
    if not fields.get("notional") and not fields.get("quantity"):
        errors.append("one of notional/quantity is required")
    return errors


def propose_order(fields: dict) -> dict | None:
    """Create a proposed order; returns None if an identical one is already open."""
    errors = validate_proposal(fields)
    if errors:
        raise ValueError("; ".join(errors))
    orders = load_orders()
    for o in orders:
        if (
            o["status"] == "proposed"
            and o["symbol"] == fields["symbol"]
            and o["action"] == fields["action"]
            and o["source"] == fields["source"]
        ):
            return None
    now = datetime.now(timezone.utc)
    order = {
        "id": make_id("order", fields["symbol"].split(".")[0]),
        "created_at": utc_now_iso(),
        "source": fields["source"],
        "action": fields["action"],
        "symbol": fields["symbol"],
        "name": fields.get("name", fields["symbol"]),
        "exchange": fields.get("exchange"),
        "currency": fields.get("currency", "USD"),
        "notional": fields.get("notional"),
        "quantity": fields.get("quantity"),
        "reference_price": fields.get("reference_price"),
        "reason": fields.get("reason", ""),
        "exit_plan": fields.get("exit_plan"),
        "expires_at": fields.get("expires_at")
        or (now + timedelta(days=ORDER_EXPIRY_DAYS)).isoformat(),
        "status": "proposed",
        "notified_at": None,
        "nag_count": 0,
        "execution": None,
        "skip_reason": None,
    }
    orders.append(order)
    save_orders(orders)
    return order


def find_order(orders: list[dict], key: str) -> dict | None:
    """Match by id, or by symbol among open orders (newest first)."""
    for o in orders:
        if o["id"] == key:
            return o
    open_matches = [
        o for o in orders
        if o["status"] == "proposed" and o["symbol"].upper().startswith(key.upper())
    ]
    return open_matches[-1] if open_matches else None


def confirm_order(key: str, price: float, quantity: float, fees: float = 0.0,
                  executed_at: str | None = None) -> dict:
    orders = load_orders()
    order = find_order(orders, key)
    if not order:
        raise ValueError(f"no open order matching '{key}'")
    if order["status"] != "proposed":
        raise ValueError(f"order {order['id']} is {order['status']}, not open")
    order["status"] = "confirmed"
    order["execution"] = {
        "price": price,
        "quantity": quantity,
        "fees": fees,
        "executed_at": executed_at or utc_now_iso(),
    }
    save_orders(orders)
    append_ledger({
        "order_id": order["id"],
        "source": order["source"],
        "action": order["action"],
        "symbol": order["symbol"],
        "currency": order["currency"],
        "price": price,
        "quantity": quantity,
        "fees": fees,
        "executed_at": order["execution"]["executed_at"],
        "recorded_at": utc_now_iso(),
    })
    return order


def skip_order(key: str, reason: str = "") -> dict:
    orders = load_orders()
    order = find_order(orders, key)
    if not order:
        raise ValueError(f"no open order matching '{key}'")
    order["status"] = "skipped"
    order["skip_reason"] = reason or "manual skip"
    save_orders(orders)
    return order


def expire_stale_orders(now: datetime | None = None) -> list[dict]:
    now = now or datetime.now(timezone.utc)
    orders = load_orders()
    expired = []
    for o in orders:
        if o["status"] != "proposed":
            continue
        try:
            exp = datetime.fromisoformat(o["expires_at"])
        except Exception:
            continue
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        if now > exp:
            o["status"] = "expired"
            expired.append(o)
    if expired:
        save_orders(orders)
    return expired


def ingest_inbox() -> list[dict]:
    """Producer contract for external strategies (e.g. aurel2 in Docker):
    drop a JSON order proposal into data/desk/inbox/ and the next desk_notify
    run validates and proposes it. Invalid files are renamed *.rejected."""
    created = []
    if not INBOX_DIR.exists():
        return created
    for path in sorted(INBOX_DIR.glob("*.json")):
        try:
            fields = json.loads(path.read_text())
            order = propose_order(fields)
            path.unlink()
            if order:
                created.append(order)
        except Exception as e:
            path.rename(path.with_suffix(".rejected"))
            print(f"  desk inbox: rejected {path.name}: {e}")
    return created


# ---------------------------------------------------------------- holdings

def compute_holdings(ledger: list[dict] | None = None,
                     now: datetime | None = None) -> dict:
    """FIFO lots per symbol from the ledger; flags lots past the 1-year mark."""
    ledger = ledger if ledger is not None else load_ledger()
    now = now or datetime.now(timezone.utc)
    lots: dict[str, list[dict]] = {}
    for e in sorted(ledger, key=lambda x: x["executed_at"]):
        sym = e["symbol"]
        if e["action"] == "buy":
            lots.setdefault(sym, []).append({
                "quantity": e["quantity"],
                "price": e["price"],
                "executed_at": e["executed_at"],
            })
        else:
            remaining = e["quantity"]
            for lot in lots.get(sym, []):
                take = min(lot["quantity"], remaining)
                lot["quantity"] -= take
                remaining -= take
                if remaining <= 1e-9:
                    break
            lots[sym] = [l for l in lots.get(sym, []) if l["quantity"] > 1e-9]
    holdings = {}
    for sym, ls in lots.items():
        if not ls:
            continue
        qty = sum(l["quantity"] for l in ls)
        cost = sum(l["quantity"] * l["price"] for l in ls)
        long_term_qty = 0.0
        for l in ls:
            dt = datetime.fromisoformat(l["executed_at"])
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            if (now - dt).days >= LONG_TERM_LOT_DAYS:
                long_term_qty += l["quantity"]
        holdings[sym] = {
            "quantity": round(qty, 6),
            "avg_price": round(cost / qty, 4),
            "cost": round(cost, 2),
            "lots": len(ls),
            "long_term_quantity": round(long_term_qty, 6),
        }
    return holdings


# ---------------------------------------------------------------- notify

def format_order_alert(order: dict, nag: bool = False) -> str:
    qty_line = (
        f"{order['quantity']} shares"
        if order.get("quantity")
        else f"~{order['notional']:.0f} {order['currency']}"
    )
    ref = f" (ref {order['reference_price']})" if order.get("reference_price") else ""
    lines = [
        f"*{'REMINDER — unexecuted order' if nag else 'MANUAL ORDER'}* — "
        f"{order['action'].upper()} {order['symbol']} ({order['name']})",
        f"Size: {qty_line}{ref}",
        f"Source: {order['source']} | Expires: {order['expires_at'][:10]}",
    ]
    if order.get("reason"):
        lines.append(f"Why: {order['reason']}")
    if order.get("exit_plan"):
        lines.append(f"Exit plan: {order['exit_plan'].get('policy', '')}")
    lines.append(
        f"Confirm with: `python3 run.py desk_confirm {order['symbol']} [PRICE] [SHARES] [FEES]`"
    )
    return "\n".join(lines)


def _send(config: dict, text: str, title: str, priority: str = "high") -> None:
    from notify import send_slack_dm, send_ntfy
    nc = config.get("notifications", {})
    runtime = config.get("runtime", {})
    if runtime.get("send_slack", True) and nc.get("slack_bot_token") and nc.get("slack_user_id"):
        send_slack_dm(nc["slack_bot_token"], nc["slack_user_id"], text)
    if runtime.get("send_ntfy", True) and nc.get("ntfy_topic"):
        send_ntfy(
            topic=nc["ntfy_topic"],
            message=text.replace("*", ""),
            title=title,
            priority=priority,
            server=nc.get("ntfy_server", "https://ntfy.sh"),
        )


def notify_pending(config: dict, now: datetime | None = None) -> int:
    """Cron entry (desk_notify): ingest inbox, expire stale, notify + nag."""
    now = now or datetime.now(timezone.utc)
    ingest_inbox()
    for o in expire_stale_orders(now):
        _send(config, f"*ORDER EXPIRED unexecuted* — {o['action'].upper()} {o['symbol']} "
                      f"({o['source']}). Logged as a deviation.",
              f"Order expired: {o['symbol']}", "high")
    orders = load_orders()
    sent = 0
    for o in orders:
        if o["status"] != "proposed":
            continue
        nag = o["notified_at"] is not None
        if nag:
            last = datetime.fromisoformat(o["notified_at"])
            if last.tzinfo is None:
                last = last.replace(tzinfo=timezone.utc)
            if (now - last).total_seconds() < NAG_INTERVAL_HOURS * 3600:
                continue
        priority = "urgent" if o["nag_count"] >= 3 else "high"
        _send(config, format_order_alert(o, nag=nag),
              f"{'Reminder' if nag else 'Order'}: {o['action']} {o['symbol']}", priority)
        o["notified_at"] = now.isoformat()
        o["nag_count"] += int(nag)
        sent += 1
    save_orders(orders)
    return sent


# ---------------------------------------------------------------- core DCA

def _first_trading_day_of_month(day: datetime) -> bool:
    """First weekday of the month (exchange holidays on day 1-3 are rare and
    only shift execution by a day — the order stays open regardless)."""
    if day.weekday() >= 5:
        return False
    return all((day - timedelta(days=i)).weekday() >= 5 for i in range(1, day.day))


def run_core_dca(config: dict, now: datetime | None = None,
                 price_fn=None) -> dict | None:
    """Monthly core buy: first trading day, notional = monthly_amount + carryover,
    skipped (carried over) while below min_ticket. Idempotent per month."""
    core = config.get("core") or {}
    amount = core.get("monthly_amount", 0)
    if not amount:
        return None
    now = now or datetime.now(timezone.utc)
    state = load_desk_state()
    month = now.strftime("%Y-%m")
    if state.get("last_dca_month") == month:
        return None
    if not _first_trading_day_of_month(now):
        return None
    carry = state.get("dca_carryover", 0.0)
    total = amount + carry
    state["last_dca_month"] = month
    if total < core.get("min_ticket", 700):
        state["dca_carryover"] = total
        save_desk_state(state)
        print(f"  core_dca: {total:.0f} below min ticket, carried over")
        return None
    state["dca_carryover"] = 0.0
    save_desk_state(state)
    ref = None
    if price_fn is None:
        from market import get_stock_data
        price_fn = lambda s: (get_stock_data(s) or {}).get("price")
    try:
        ref = price_fn(core.get("symbol", "SXR8.DE"))
    except Exception:
        ref = None
    order = propose_order({
        "source": "core_dca",
        "action": "buy",
        "symbol": core.get("symbol", "SXR8.DE"),
        "name": core.get("name", "iShares Core S&P 500 UCITS ETF (Acc)"),
        "exchange": core.get("exchange", "XETRA"),
        "currency": core.get("currency", "EUR"),
        "notional": round(total, 2),
        "reference_price": ref,
        "reason": "Monthly core contribution. Buys every month regardless of "
                  "market conditions — discipline beat panic-selling in 92% and "
                  "dip-waiting in 100% of 10-year windows since 1993.",
    })
    return order


# ---------------------------------------------------------------- guard

GUARD_THRESHOLDS = (-0.10, -0.20, -0.30)


def run_core_guard(config: dict, now: datetime | None = None,
                   history_fn=None) -> list[str]:
    """Anti-panic pre-commitment: on each new drawdown threshold, send the
    'plan says do nothing' message once per drawdown episode."""
    core = config.get("core") or {}
    proxy = core.get("index_proxy", "SPY")
    if history_fn is None:
        def history_fn(sym):
            import yfinance as yf
            h = yf.Ticker(sym).history(period="max", auto_adjust=True)
            return [float(x) for x in h["Close"]]
    closes = history_fn(proxy)
    if not closes:
        return []
    ath = max(closes)
    price = closes[-1]
    dd = price / ath - 1
    state = load_desk_state()
    guard = state.get("guard", {"ath": 0.0, "sent": {}})
    if ath > guard.get("ath", 0.0) * 1.001:
        guard = {"ath": ath, "sent": {}}  # new high — episode reset
    fired = []
    for th in GUARD_THRESHOLDS:
        key = f"{th:.2f}"
        if dd <= th and key not in guard["sent"]:
            guard["sent"][key] = utc_now_iso()
            msg = (
                f"*MARKET DROP — the plan says: do nothing.*\n"
                f"S&P 500 is {dd:+.0%} from its high. This is within the plan. "
                f"Panic-selling at -20% cost a median EUR 7,000 per decade across "
                f"95 backtest windows (1993-2026). The monthly buy proceeds as "
                f"scheduled. Selling now would also trigger 6% tax on any gains."
            )
            _send(config, msg, f"Drawdown {dd:+.0%}: hold", "high")
            fired.append(key)
    state["guard"] = guard
    save_desk_state(state)
    return fired


# ---------------------------------------------------------------- status

def format_status(now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    orders = load_orders()
    holdings = compute_holdings(now=now)
    lines = ["=== Desk status ==="]
    open_orders = [o for o in orders if o["status"] == "proposed"]
    lines.append(f"Open orders: {len(open_orders)}")
    for o in open_orders:
        size = f"{o['quantity']} sh" if o.get("quantity") else f"{o['notional']} {o['currency']}"
        lines.append(f"  {o['id']} | {o['action']} {o['symbol']} {size} | "
                     f"source {o['source']} | expires {o['expires_at'][:10]}")
    lines.append(f"Holdings: {len(holdings)}")
    for sym, h in sorted(holdings.items()):
        lt = f", {h['long_term_quantity']} long-term (3% tax)" if h["long_term_quantity"] else ""
        lines.append(f"  {sym}: {h['quantity']} @ avg {h['avg_price']} "
                     f"(cost {h['cost']}, {h['lots']} lots{lt})")
    skipped = [o for o in orders if o["status"] in ("skipped", "expired")]
    if skipped:
        lines.append(f"Deviations (skipped/expired): {len(skipped)}")
        for o in skipped[-5:]:
            lines.append(f"  {o['created_at'][:10]} {o['action']} {o['symbol']} -> "
                         f"{o['status']} ({o.get('skip_reason') or 'unexecuted'})")
    state = load_desk_state()
    if state.get("dca_carryover"):
        lines.append(f"DCA carryover: {state['dca_carryover']}")
    return "\n".join(lines)
