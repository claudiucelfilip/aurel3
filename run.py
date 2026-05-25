#!/usr/bin/env python3
"""Aurel3 — signal engine + watchlist thesis manager.

Usage:
  python3 /root/aurel3/run.py openclaw_cycle
  python3 /root/aurel3/run.py openclaw_run
  python3 /root/aurel3/run.py signal_scan
  python3 /root/aurel3/run.py watchlist_review
  python3 /root/aurel3/run.py openclaw_status
  python3 /root/aurel3/run.py openclaw_export
  python3 /root/aurel3/run.py openclaw_prepare
  python3 /root/aurel3/run.py openclaw_import PATH [--force]
  python3 /root/aurel3/run.py status
  python3 /root/aurel3/run.py performance
  python3 /root/aurel3/run.py buy TICKER [PRICE] [SHARES]
  python3 /root/aurel3/run.py sell TICKER [PRICE]
  python3 /root/aurel3/run.py postmortem [TICKER]
  python3 /root/aurel3/run.py review_signals [TICKER]
  python3 /root/aurel3/run.py review_summary
  python3 /root/aurel3/run.py notify_failure COMMAND EXIT_CODE

Aliases:
  scan -> signal_scan
  watch -> watchlist_review
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from market import get_stock_data


MAX_PRICE_DEVIATION_PCT = 0.35
MIN_REASONABLE_PRICE = 0.01


def _parse_positive_float(value: str, field_name: str) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        print(f"Invalid {field_name}: {value}")
        return None
    if parsed <= 0:
        print(f"Invalid {field_name}: must be > 0")
        return None
    return parsed


def _validate_price_against_market(ticker: str, entered_price: float, market_data: dict | None, side: str) -> bool:
    if entered_price < MIN_REASONABLE_PRICE:
        print(f"Rejected {side} for {ticker}: price must be at least ${MIN_REASONABLE_PRICE:.2f}.")
        return False

    if not market_data or not market_data.get("price"):
        return True

    market_price = float(market_data["price"])
    deviation_pct = abs((entered_price / market_price) - 1)
    if deviation_pct > MAX_PRICE_DEVIATION_PCT:
        print(
            f"Rejected {side} for {ticker}: entered price ${entered_price:.2f} looks implausible vs "
            f"market price ${market_price:.2f} ({deviation_pct:+.1%} deviation)."
        )
        return False

    return True
from notify import (
    send_failure_alert,
    send_recommendation_alert,
    send_watchlist_action_alert,
    send_postmortem_summary,
)
from openclaw_bridge import load_fresh_interpreted_items
from reviews import (
    build_closed_position_review,
    build_recommendation_review,
    recommendation_is_mature,
)
from signals import generate_signal_scan
from sources import collect_source_items
from sentiment import analyze_mention_sentiment
from state import (
    append_closed_review,
    append_recommendation_snapshot,
    append_recommendation_review,
    load_closed_reviews,
    load_recommendations,
    load_recommendation_history,
    load_recommendation_reviews,
    load_theme_events,
    mark_recommendation_promoted,
    save_recommendations,
    save_theme_events,
    find_latest_active_recommendation,
    load_openclaw_interpreted_items,
    load_openclaw_source_batch,
)
from watchlist import (
    add_position,
    close_position,
    find_position,
    get_open_positions,
    get_performance_summary,
    load_history,
    review_position,
    save_reviewed_positions,
    should_send_action_alert,
)

CONFIG_PATH = Path(__file__).parent / "config.json"


def load_config() -> dict:
    with open(CONFIG_PATH) as f:
        config = json.load(f)

    nc = config.setdefault("notifications", {})
    runtime = config.setdefault("runtime", {})
    runtime.setdefault("enable_news", True)
    runtime.setdefault("enable_social", True)
    runtime.setdefault("send_slack", True)
    runtime.setdefault("send_ntfy", True)
    runtime.setdefault("require_openclaw_interpretation", True)

    slack_token_env = nc.get("slack_bot_token_env")
    slack_user_env = nc.get("slack_user_id_env")
    ntfy_topic_env = nc.get("ntfy_topic_env")
    ntfy_server_env = nc.get("ntfy_server_env")

    if slack_token_env and os.getenv(slack_token_env):
        nc["slack_bot_token"] = os.getenv(slack_token_env, "")
    if slack_user_env and os.getenv(slack_user_env):
        nc["slack_user_id"] = os.getenv(slack_user_env, "")
    if ntfy_topic_env and os.getenv(ntfy_topic_env):
        nc["ntfy_topic"] = os.getenv(ntfy_topic_env, nc.get("ntfy_topic", "aurel3"))
    if ntfy_server_env and os.getenv(ntfy_server_env):
        nc["ntfy_server"] = os.getenv(ntfy_server_env, nc.get("ntfy_server", "https://ntfy.sh"))

    return config


def cmd_signal_scan() -> None:
    config = load_config()
    source_items = collect_source_items()
    if config.get("runtime", {}).get("require_openclaw_interpretation", True):
        interpreted_items = load_fresh_interpreted_items()
        if not interpreted_items:
            print(
                "Signal scan aborted: no fresh OpenClaw-interpreted items available. "
                "Run the OpenClaw interpretation cycle first."
            )
            return
    themes, recommendations = generate_signal_scan(source_items)

    save_theme_events(themes)
    save_recommendations(recommendations)
    append_recommendation_snapshot(
        recommendations,
        metadata={
            "source": "signal_scan",
            "source_items": {
                "social": len(source_items.get("social", [])),
                "raw_social": len(source_items.get("raw_social", [])),
                "news": len(source_items.get("news", [])),
            },
        },
    )

    actionable = [rec for rec in recommendations if rec["action"] == "buy_now"]
    open_tickers = {pos["ticker"].upper() for pos in get_open_positions()}
    actionable_new = [rec for rec in actionable if rec["ticker"].upper() not in open_tickers]
    skipped = len(actionable) - len(actionable_new)
    action_counts: dict[str, int] = {}
    gate_counts: dict[str, int] = {}
    for rec in recommendations:
        action_counts[rec["action"]] = action_counts.get(rec["action"], 0) + 1
        for reason in rec.get("gate_reasons", []):
            gate_counts[reason] = gate_counts.get(reason, 0) + 1
    print(
        f"Signal scan completed: {len(recommendations)} recommendations, "
        f"{len(actionable)} buy-now ideas ({skipped} already on watchlist)."
    )
    if action_counts:
        print("  Actions: " + ", ".join(f"{k}={v}" for k, v in sorted(action_counts.items())))
    if gate_counts:
        top_gates = sorted(gate_counts.items(), key=lambda item: (-item[1], item[0]))[:5]
        print("  Top non-buy gates: " + ", ".join(f"{k}={v}" for k, v in top_gates))
    for rec in recommendations[:5]:
        gates = ", ".join(rec.get("gate_reasons", [])[:3]) or "none"
        print(
            f"  TOP: {rec['ticker']} -> {rec['action']} "
            f"[{rec['confirmation_state']}, {rec['confidence']}] gates={gates}"
        )

    for rec in actionable_new:
        print(f"  BUY NOW: {rec['ticker']} — {rec['theme_driver']} [{rec['confirmation_state']}, {rec['confidence']}]")
        for alt in rec.get("alternatives", []):
            print(
                "    ALT: "
                f"{alt['ticker']} [{alt['action']}, {alt['confirmation_state']}, {alt['confidence']}]"
            )
        send_recommendation_alert(config, rec)


def cmd_watchlist_review() -> None:
    config = load_config()
    positions = get_open_positions()
    if not positions:
        print("Watchlist is empty.")
        return

    source_items = collect_source_items()
    social_lookup = {}
    for item in source_items.get("social", []):
        payload = item["payload"]
        social_lookup[payload["ticker"]] = analyze_mention_sentiment(payload)

    reviewed: list[dict] = []
    actionable = 0
    for pos in positions:
        data = get_stock_data(pos["ticker"])
        if not data:
            reviewed.append(pos)
            continue

        updated = review_position(pos, data, social_lookup=social_lookup)
        reviewed.append(updated)

        if should_send_action_alert(pos, updated):
            actionable += 1
            print(f"  ACTION: {updated['ticker']} -> {updated['current_action']} [{updated['exit_urgency']}]")
            send_watchlist_action_alert(config, updated, data)

    save_reviewed_positions(reviewed)
    print(f"Watchlist review completed: {len(reviewed)} positions checked, {actionable} actionable changes.")


def cmd_status() -> None:
    positions = get_open_positions()
    if not positions:
        print("Watchlist is empty.")
        return

    print(f"Open positions ({len(positions)}):")
    for pos in positions:
        data = get_stock_data(pos["ticker"])
        price_str = f"${data['price']:.2f}" if data else "N/A"
        pnl = ""
        if data:
            pnl_pct = (data["price"] / pos["entry_price"]) - 1
            pnl = f" ({pnl_pct:+.1%})"
        print(
            f"  {pos['ticker']}: {price_str}{pnl} | "
            f"Thesis: {pos.get('current_thesis_state', 'n/a')} | "
            f"Confirm: {pos.get('current_confirmation_state', 'n/a')} | "
            f"Action: {pos.get('current_action', 'hold')}"
        )


def cmd_openclaw_status() -> None:
    batch = load_openclaw_source_batch()
    interpreted = load_openclaw_interpreted_items()
    fresh_items = load_fresh_interpreted_items()
    print("OpenClaw Status:")
    print(f"  Source batch generated_at: {batch.get('generated_at')}")
    print(f"  Source batch items: {len(batch.get('items', []))}")
    print(f"  Interpreted payload generated_at: {interpreted.get('generated_at')}")
    print(f"  Interpreted payload items: {len(interpreted.get('items', []))}")
    print(f"  Fresh interpreted items currently usable: {len(fresh_items)}")


def cmd_openclaw_export() -> None:
    source_items = collect_source_items(export_batch=True)
    batch = load_openclaw_source_batch()
    print("OpenClaw export complete:")
    print(f"  Batch generated_at: {batch.get('generated_at')}")
    print(f"  Batch items: {len(batch.get('items', []))}")
    print(f"  Live social items: {len(source_items.get('social', []))}")
    print(f"  Live news items: {len(source_items.get('news', []))}")


def cmd_openclaw_prepare() -> None:
    result = subprocess.run(
        ["python3", "openclaw_prepare.py"],
        cwd=str(Path(__file__).parent),
        capture_output=True,
        text=True,
    )
    if result.stdout:
        print(result.stdout.strip())
    if result.stderr:
        print(result.stderr.strip())
    if result.returncode != 0:
        raise SystemExit(result.returncode)


def cmd_openclaw_import(path: str, force: bool = False) -> None:
    cmd = ["python3", "openclaw_import.py", path]
    if force:
        cmd.append("--force")
    result = subprocess.run(
        cmd,
        cwd=str(Path(__file__).parent),
        capture_output=True,
        text=True,
    )
    if result.stdout:
        print(result.stdout.strip())
    if result.stderr:
        print(result.stderr.strip())
    if result.returncode != 0:
        raise SystemExit(result.returncode)


def cmd_openclaw_run() -> None:
    result = subprocess.run(
        ["python3", "openclaw_run.py"],
        cwd=str(Path(__file__).parent),
        capture_output=True,
        text=True,
    )
    if result.stdout:
        print(result.stdout.strip())
    if result.stderr:
        print(result.stderr.strip())
    if result.returncode != 0:
        raise SystemExit(result.returncode)


def cmd_openclaw_cycle() -> None:
    result = subprocess.run(
        ["python3", "openclaw_cycle.py"],
        cwd=str(Path(__file__).parent),
        capture_output=True,
        text=True,
    )
    if result.stdout:
        print(result.stdout.strip())
    if result.stderr:
        print(result.stderr.strip())
    if result.returncode != 0:
        raise SystemExit(result.returncode)


def cmd_buy(ticker: str, price: str | None = None, shares: str | None = None) -> None:
    ticker = ticker.upper()
    recommendation = find_latest_active_recommendation(ticker)
    data = get_stock_data(ticker)

    if price:
        entry_price = _parse_positive_float(price, "price")
        if entry_price is None:
            return
    else:
        if data and data["price"] > 0:
            entry_price = data["price"]
        else:
            print(f"Couldn't get price for {ticker}. Specify: buy TICKER PRICE [SHARES]")
            return

    if not _validate_price_against_market(ticker, entry_price, data, "buy"):
        return

    num_shares = _parse_positive_float(shares, "shares") if shares else 0
    if shares and num_shares is None:
        return

    pos = add_position(
        ticker=ticker,
        entry_price=entry_price,
        shares=num_shares,
        recommendation=recommendation,
    )
    if recommendation:
        mark_recommendation_promoted(recommendation["id"])

    invested = f" (${entry_price * num_shares:.2f} invested)" if num_shares > 0 else ""
    print(
        f"Added {ticker} to watchlist at ${entry_price:.2f}{invested} | "
        f"Theme: {pos.get('original_theme_driver')}"
    )


def cmd_sell(ticker: str, price: str | None = None) -> None:
    ticker = ticker.upper()
    data = get_stock_data(ticker)
    sell_price = _parse_positive_float(price, "price") if price else None
    if price and sell_price is None:
        return
    if not sell_price:
        if data and data["price"] > 0:
            sell_price = data["price"]

    if sell_price and not _validate_price_against_market(ticker, sell_price, data, "sell"):
        return

    result = close_position(ticker, sell_price=sell_price)
    if not result:
        print(f"{ticker} not found in open watchlist.")
        return

    review = build_closed_position_review(result)
    append_closed_review(review)

    pnl_pct = result.get("pnl_pct", 0)
    pnl_dollar = result.get("pnl_dollar", 0)
    print(f"Closed {ticker} at ${sell_price:.2f} — {pnl_pct:+.1%}, ${pnl_dollar:+.2f}")


def cmd_postmortem(ticker: str | None = None) -> None:
    reviews = load_closed_reviews()
    if ticker:
        reviews = [r for r in reviews if r.get("ticker") == ticker.upper()]
    if not reviews:
        print("No closed-position reviews found.")
        return

    review = reviews[-1]
    print(
        f"Postmortem {review['ticker']}: outcome={review['thesis_outcome']} "
        f"| failure={review['failure_point']} | lesson={review['lesson']}"
    )
    config = load_config()
    send_postmortem_summary(config, review)


def cmd_review_signals(ticker: str | None = None) -> None:
    reviewed_ids = {r.get("recommendation_id") for r in load_recommendation_reviews()}
    recommendations = load_recommendations()
    history = load_recommendation_history()
    for snapshot in history:
        for rec in snapshot.get("recommendations", []):
            if rec.get("id") and not any(existing.get("id") == rec.get("id") for existing in recommendations):
                recommendations.append(rec)
    if ticker:
        recommendations = [r for r in recommendations if r.get("ticker") == ticker.upper()]

    created = 0
    skipped_reviewed = 0
    skipped_immature = 0
    skipped_no_price = 0
    skipped_no_market_data = 0
    for rec in recommendations:
        if rec.get("id") in reviewed_ids:
            skipped_reviewed += 1
            continue
        if not recommendation_is_mature(rec):
            skipped_immature += 1
            continue
        if not rec.get("reference_price"):
            skipped_no_price += 1
            continue
        data = get_stock_data(rec["ticker"])
        if not data:
            skipped_no_market_data += 1
            continue

        review = build_recommendation_review(rec, data["price"])
        append_recommendation_review(review)
        created += 1
        print(
            f"  SIGNAL REVIEW: {review['ticker']} -> {review['outcome']} "
            f"({review['forward_return_pct']:+.1%}) | {review['summary']}"
        )

    if created == 0:
        print("No matured recommendation reviews created.")
    else:
        print(f"Created {created} recommendation review(s).")
    print(
        "Review candidates: "
        f"total={len(recommendations)}, reviewed={skipped_reviewed}, immature={skipped_immature}, "
        f"missing_reference_price={skipped_no_price}, missing_market_data={skipped_no_market_data}."
    )


def cmd_review_summary() -> None:
    closed_reviews = load_closed_reviews()
    signal_reviews = load_recommendation_reviews()
    recommendations = load_recommendations()

    print("Review Summary:")

    if closed_reviews:
        outcome_counts: dict[str, int] = {}
        failure_counts: dict[str, int] = {}
        for review in closed_reviews:
            outcome = review.get("thesis_outcome", "unknown")
            outcome_counts[outcome] = outcome_counts.get(outcome, 0) + 1
            failure = review.get("failure_point", "unknown")
            failure_counts[failure] = failure_counts.get(failure, 0) + 1

        print(f"  Trade reviews: {len(closed_reviews)}")
        print("  Trade outcomes: " + ", ".join(f"{k}={v}" for k, v in sorted(outcome_counts.items())))
        print("  Trade failure points: " + ", ".join(f"{k}={v}" for k, v in sorted(failure_counts.items())))
    else:
        print("  Trade reviews: none")

    if signal_reviews:
        outcome_counts = {}
        for review in signal_reviews:
            outcome = review.get("outcome", "unknown")
            outcome_counts[outcome] = outcome_counts.get(outcome, 0) + 1
        print(f"  Signal reviews: {len(signal_reviews)}")
        print("  Signal outcomes: " + ", ".join(f"{k}={v}" for k, v in sorted(outcome_counts.items())))
    else:
        print("  Signal reviews: none")

    active_recs = [rec for rec in recommendations if rec.get("status") == "active"]
    if active_recs:
        print("  Active themes:")
        for rec in active_recs[:5]:
            print(
                f"    {rec['theme_driver']} -> {rec['ticker']} "
                f"({rec['action']}, {rec['confirmation_state']}, {rec['confidence']})"
            )
    else:
        print("  Active themes: none")

    spec_candidates = [
        review for review in signal_reviews if review.get("spec_change_candidate")
    ] + [
        review for review in closed_reviews if review.get("spec_change_candidate")
    ]
    print(f"  Spec change candidates: {len(spec_candidates)}")


def cmd_notify_failure(command: str, exit_code: str) -> None:
    """Send a Slack alert when a cron command exits non-zero.

    Called from cron.sh after the wrapped python invocation fails. Reads
    the tail of runtime.log to give the alert recipient enough context to
    triage without SSHing to the box.
    """
    config = load_config()
    log_path = Path(__file__).parent / "data" / "runtime.log"
    excerpt = ""
    if log_path.exists():
        try:
            with open(log_path) as f:
                excerpt = "".join(f.readlines()[-30:])
        except Exception as exc:
            excerpt = f"(could not read runtime.log: {exc})"
    sent = send_failure_alert(config, command, exit_code, excerpt)
    print(f"Failure alert {'sent' if sent else 'NOT sent (slack disabled or unconfigured)'}: {command} exit={exit_code}")


def cmd_performance() -> None:
    summary = get_performance_summary()
    if summary["total_trades"] == 0:
        print("No completed trades yet.")
        return

    print(f"Performance Summary ({summary['total_trades']} trades):")
    print(f"  Win rate: {summary['win_rate']:.0%} ({summary['wins']}W / {summary['losses']}L)")
    print(f"  Total P&L: ${summary['total_pnl_dollar']:+.2f}")
    print(f"  Avg return: {summary['avg_pnl_pct']:+.1%}")
    print(f"  Avg hold: {summary['avg_hold_days']:.1f} days")

    history = load_history()
    if history:
        print("\nRecent trades:")
        for t in history[-10:]:
            dollar_str = f" ${t.get('pnl_dollar', 0):+.2f}" if t.get("pnl_dollar") else ""
            reason = f" | {t.get('close_reason')}" if t.get("close_reason") else ""
            print(
                f"  {t['ticker']}: ${t['entry_price']:.2f} → ${t.get('sell_price', 0):.2f} "
                f"= {t['pnl_pct']:+.1%}{dollar_str} ({t.get('days_held', 0)}d){reason}"
            )


def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        return

    command = sys.argv[1].lower()
    if command == "scan":
        command = "signal_scan"
    elif command == "watch":
        command = "watchlist_review"

    if command == "signal_scan":
        cmd_signal_scan()
    elif command == "watchlist_review":
        cmd_watchlist_review()
    elif command == "status":
        cmd_status()
    elif command == "openclaw_status":
        cmd_openclaw_status()
    elif command == "openclaw_cycle":
        cmd_openclaw_cycle()
    elif command == "openclaw_export":
        cmd_openclaw_export()
    elif command == "openclaw_prepare":
        cmd_openclaw_prepare()
    elif command == "openclaw_run":
        cmd_openclaw_run()
    elif command == "openclaw_import":
        path = sys.argv[2] if len(sys.argv) >= 3 else None
        force = len(sys.argv) >= 4 and sys.argv[3] == "--force"
        if not path:
            print("Usage: openclaw_import PATH")
        else:
            cmd_openclaw_import(path, force=force)
    elif command == "performance":
        cmd_performance()
    elif command == "notify_failure":
        failed_cmd = sys.argv[2] if len(sys.argv) >= 3 else "?"
        exit_code = sys.argv[3] if len(sys.argv) >= 4 else "?"
        cmd_notify_failure(failed_cmd, exit_code)
    elif command == "buy":
        ticker = sys.argv[2] if len(sys.argv) >= 3 else None
        price = sys.argv[3] if len(sys.argv) >= 4 else None
        shares = sys.argv[4] if len(sys.argv) >= 5 else None
        if not ticker:
            print("Usage: buy TICKER [PRICE] [SHARES]")
        else:
            cmd_buy(ticker, price, shares)
    elif command == "sell":
        ticker = sys.argv[2] if len(sys.argv) >= 3 else None
        price = sys.argv[3] if len(sys.argv) >= 4 else None
        if not ticker:
            print("Usage: sell TICKER [PRICE]")
        else:
            cmd_sell(ticker, price)
    elif command == "postmortem":
        ticker = sys.argv[2] if len(sys.argv) >= 3 else None
        cmd_postmortem(ticker)
    elif command == "review_signals":
        ticker = sys.argv[2] if len(sys.argv) >= 3 else None
        cmd_review_signals(ticker)
    elif command == "review_summary":
        cmd_review_summary()
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
