"""Notifications for Aurel3."""

from __future__ import annotations

import httpx


def send_slack_dm(bot_token: str, user_id: str, text: str) -> bool:
    try:
        resp = httpx.post(
            "https://slack.com/api/conversations.open",
            headers={"Authorization": f"Bearer {bot_token}"},
            json={"users": user_id},
            timeout=20,
        )
        data = resp.json()
        if not data.get("ok"):
            print(f"  Slack conversations.open failed: {data.get('error')}")
            return False

        channel = data["channel"]["id"]
        resp = httpx.post(
            "https://slack.com/api/chat.postMessage",
            headers={"Authorization": f"Bearer {bot_token}"},
            json={"channel": channel, "text": text},
            timeout=20,
        )
        data = resp.json()
        if not data.get("ok"):
            print(f"  Slack chat.postMessage failed: {data.get('error')}")
            return False
        return True
    except Exception as e:
        print(f"  Slack error: {e}")
        return False


def _ntfy_priority_int(priority: str) -> int:
    return {"min": 1, "low": 2, "default": 3, "high": 4, "urgent": 5}.get(priority, 3)


def send_ntfy(
    topic: str,
    message: str,
    title: str | None = None,
    priority: str = "high",
    tags: list[str] | None = None,
    server: str = "https://ntfy.sh",
) -> bool:
    try:
        payload = {"topic": topic, "message": message}
        if title:
            payload["title"] = title
        if priority:
            payload["priority"] = _ntfy_priority_int(priority)
        if tags:
            payload["tags"] = tags
        resp = httpx.post(server, json=payload, timeout=20)
        return resp.status_code == 200
    except Exception as e:
        print(f"  ntfy error: {e}")
        return False


def format_recommendation_alert(rec: dict) -> str:
    market_line = rec.get("market_exchange", "UNKNOWN")
    if rec.get("market_region"):
        market_line = f"{market_line} / {rec['market_region']}"
    social = rec.get("social_evidence") or {}
    social_line = None
    if social:
        if social.get("is_trending"):
            social_line = (
                f"Social: mentions {social.get('mentions', 0)} ({social.get('mention_change', 0):+.0%}), "
                f"rank {('#' + str(social.get('rank_24h_ago')) + '→#' + str(social.get('rank'))) if social.get('rank') and social.get('rank_24h_ago') else 'n/a'}, "
                f"upvotes {social.get('upvotes', 0)}, sources {len(social.get('sources', []))}, "
                f"momentum {social.get('momentum', 'unknown')}"
            )
        else:
            social_line = "Social: not trending on tracked Reddit sources"

    lines = [
        f"*{rec['action'].replace('_', ' ').upper()}* — {rec['ticker']} ({rec['company']})",
        f"Market: {market_line}",
        f"Driver: {rec['theme_driver']}",
        f"Why now: {rec['why_now']}",
        f"Confirmation: {rec['confirmation_state']} | Confidence: {rec['confidence']} | Horizon: {rec['expected_horizon']}",
        f"Invalidation: {rec['invalidation']}",
    ]
    if social_line:
        lines.insert(4, social_line)
    if rec.get("alternatives"):
        alt_lines = []
        for alt in rec["alternatives"]:
            alt_lines.append(
                f"{alt['ticker']} ({alt['action'].replace('_', ' ')}, "
                f"{alt['confirmation_state']}, {alt['confidence']})"
            )
        lines.append(f"Alternative: {'; '.join(alt_lines)}")
    if rec.get("action") == "buy_now":
        lines.append(f"Action template: `buy {rec['ticker']} [PRICE] [SHARES]`")
    return "\n".join(lines)


def format_watchlist_action_alert(position: dict, market_data: dict) -> str:
    price = market_data.get("price")
    price_part = f"${price:.2f}" if price else "N/A"
    lines = [
        f"*{position['current_action'].replace('_', ' ').upper()}* — {position['ticker']} ({position['company']})",
        f"Thesis: {position['current_thesis_state']} | Confirmation: {position['current_confirmation_state']} | Urgency: {position['exit_urgency']}",
        f"Price: {price_part}",
        f"Reason: {position.get('current_action_reason', 'Actionable thesis change detected.')}",
    ]
    action = position.get("current_action")
    if action == "sell":
        lines.append(f"Action template: `sell {position['ticker']} [PRICE]`")
    elif action == "trim_de_risk":
        lines.append(f"Action template: `sell {position['ticker']} [PRICE]`")
    return "\n".join(lines)


def format_postmortem_summary(review: dict) -> str:
    pnl = review.get("realized_pnl", {})
    return "\n".join([
        f"*POSTMORTEM* — {review['ticker']}",
        f"Outcome: {review['thesis_outcome']} | Failure point: {review['failure_point']}",
        f"P&L: {pnl.get('pnl_pct', 0):+.1%} ({pnl.get('pnl_amount', 0):+.2f} {pnl.get('currency', '')})",
        f"Lesson: {review['lesson']}",
    ])


def format_failure_alert(command: str, exit_code: str, log_excerpt: str) -> str:
    from datetime import datetime, timezone
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    excerpt_lines = [line for line in log_excerpt.splitlines() if line.strip()]
    if len(excerpt_lines) > 20:
        excerpt_lines = excerpt_lines[-20:]
    excerpt = "\n".join(excerpt_lines) or "(no log output)"
    return "\n".join([
        f"*AUREL3 CRON FAILED* — `{command}` (exit {exit_code})",
        ts,
        "",
        "Last log lines:",
        f"```\n{excerpt}\n```",
    ])


def send_recommendation_alert(config: dict, recommendation: dict) -> bool:
    # Check if ticker is already on the watchlist — skip notification if so
    from watchlist import find_position
    ticker = recommendation["ticker"].upper()
    if find_position(ticker, status="open"):
        return False  # Already on watchlist, do not notify

    nc = config["notifications"]
    text = format_recommendation_alert(recommendation)
    runtime = config.get("runtime", {})
    slack_ok = False
    if runtime.get("send_slack", True) and nc.get("slack_bot_token") and nc.get("slack_user_id"):
        slack_ok = send_slack_dm(nc["slack_bot_token"], nc["slack_user_id"], text)

    if runtime.get("send_ntfy", True) and nc.get("ntfy_topic") and recommendation["action"] == "buy_now":
        send_ntfy(
            topic=nc["ntfy_topic"],
            message=f"{recommendation['ticker']} | {recommendation['theme_driver']}",
            title=f"BUY NOW {recommendation['ticker']}",
            priority="high",
            tags=["chart_with_upwards_trend"],
            server=nc.get("ntfy_server", "https://ntfy.sh"),
        )
    return slack_ok


def send_watchlist_action_alert(config: dict, position: dict, market_data: dict) -> bool:
    nc = config["notifications"]
    text = format_watchlist_action_alert(position, market_data)
    runtime = config.get("runtime", {})
    slack_ok = False
    if runtime.get("send_slack", True) and nc.get("slack_bot_token") and nc.get("slack_user_id"):
        slack_ok = send_slack_dm(nc["slack_bot_token"], nc["slack_user_id"], text)

    action = position.get("current_action")
    if runtime.get("send_ntfy", True) and nc.get("ntfy_topic") and action in ("sell", "trim_de_risk"):
        priority = "urgent" if action == "sell" or position.get("exit_urgency") == "high" else "high"
        send_ntfy(
            topic=nc["ntfy_topic"],
            message=f"{position['ticker']} | {position.get('current_action_reason', action)}",
            title=f"{action.replace('_', ' ').upper()} {position['ticker']}",
            priority=priority,
            tags=["warning"],
            server=nc.get("ntfy_server", "https://ntfy.sh"),
        )
    return slack_ok


def send_postmortem_summary(config: dict, review: dict) -> bool:
    nc = config["notifications"]
    text = format_postmortem_summary(review)
    runtime = config.get("runtime", {})
    if runtime.get("send_slack", True) and nc.get("slack_bot_token") and nc.get("slack_user_id"):
        return send_slack_dm(nc["slack_bot_token"], nc["slack_user_id"], text)
    return False


def send_failure_alert(config: dict, command: str, exit_code: str, log_excerpt: str) -> bool:
    """Notify Slack when a cron command exits non-zero.

    Mirrors the existing alert path so the failure surfaces in the same DM
    channel as buy/sell signals — without this, a stalled pipeline (e.g.
    Gemini quota exhaustion in early April 2026) goes unnoticed for days.
    """
    nc = config.get("notifications", {})
    text = format_failure_alert(command, exit_code, log_excerpt)
    runtime = config.get("runtime", {})
    if runtime.get("send_slack", True) and nc.get("slack_bot_token") and nc.get("slack_user_id"):
        return send_slack_dm(nc["slack_bot_token"], nc["slack_user_id"], text)
    return False
