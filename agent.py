"""Orchestrator: news -> LLM -> risk -> paper broker -> log (steps 1-6)."""
from __future__ import annotations
from dataclasses import asdict
from typing import Any

from . import broker as broker_mod
from . import config, logger, risk
from .llm import Signal
from .news import NewsEvent


def run_event(event: NewsEvent, equity: float, news_origin: str = "manual input") -> dict[str, Any]:
    """Run the FULL flow for one event. Returns the log record (also persisted)."""
    ts = logger.utc_now_iso()
    bro = broker_mod.PaperBroker(equity)

    # Late import avoids circulars (llm/broker don't import agent).
    from .llm import interpret_event

    # 1-3. Interpret ---------------------------------------------------------
    signal: Signal = interpret_event(event.text())
    record: dict[str, Any] = {
        "timestamp": ts, "mode": "PAPER ONLY",
        "event": {"title": event.title, "source": event.source,
                  "published": event.published, "news_origin": news_origin},
        "interpretation": {"engine": signal.engine, "reasoning": signal.reasoning,
                           "confidence": signal.confidence},
        "decision": {"trade": signal.trade, "ticker": signal.ticker,
                     "direction": signal.direction,
                     "requested_size_pct": signal.size_pct},
        "risk": {}, "order": None, "result": "",
    }

    # 2b. No-trade path is a first-class, logged outcome ----------------------
    if not signal.trade:
        record["risk"] = {"checked": False, "reason": "No trade signal — risk gate not needed."}
        record["result"] = "NO_TRADE: flat. Capital preserved; no order placed."
        _print_run(record)
        logger.log_run(record)
        return record

    # 4. Hard risk gate (BEFORE any order) ------------------------------------
    state = risk.RiskState(equity=equity, day_pnl_pct=bro.day_pnl_pct(),
                           open_positions=bro.open_position_count(),
                           halted=bro.is_halted())
    verdict = risk.check(float(signal.size_pct or 0), state)
    record["risk"] = {"checked": True, "approved": verdict.approved,
                      "reasons": verdict.reasons,
                      "capped_size_pct": verdict.capped_size_pct,
                      "stop_pct": verdict.stop_pct,
                      "state": asdict(state),
                      "limits": {"max_position_pct": config.MAX_POSITION_PCT,
                                 "daily_loss_limit_pct": config.DAILY_LOSS_LIMIT_PCT,
                                 "max_open_positions": config.MAX_OPEN_POSITIONS,
                                 "stop_loss_pct": config.STOP_LOSS_PCT}}
    if not verdict.approved:
        record["result"] = "BLOCKED by risk gate — no order placed. " + " | ".join(verdict.reasons)
        _print_run(record)
        logger.log_run(record)
        return record

    # 5. Paper order (only reachable after approval) ---------------------------
    order = bro.place_order(signal.ticker or "", signal.direction or "",
                            verdict.capped_size_pct)
    record["order"] = asdict(order)
    record["result"] = (
        f"PAPER {order.direction.upper()} {order.ticker} {order.size_pct}% "
        f"(≈${order.notional_usd:,.2f} @ ${order.price}) | stop {order.stop_pct}% "
        f"→ {order.stop_price} | id {order.order_id} | {order.status}"
    )
    _print_run(record)
    logger.log_run(record)
    return record


def _print_run(r: dict[str, Any]) -> None:
    logger.header("EVENT-DRIVEN rTOKEN AGENT (paper)")
    logger.step(f"timestamp : {r['timestamp']} (UTC) · mode: {r['mode']}")
    logger.step(f"event     : {r['event']['title']}")
    logger.step(f"source    : {r['event']['source']} · via {r['event']['news_origin']}")
    logger.header("Interpretation")
    logger.step(f"engine    : {r['interpretation']['engine']}")
    logger.step(f"reasoning : {r['interpretation']['reasoning']}")
    logger.step(f"confidence: {r['interpretation']['confidence']}")
    d = r["decision"]
    logger.header("Decision")
    if d["trade"]:
        logger.step(f"SIGNAL    : {d['direction'].upper()} {d['ticker']} "
                    f"size={d['requested_size_pct']}% confidence={r['interpretation']['confidence']}")
    else:
        logger.step("SIGNAL    : NO_TRADE (stay flat)")
    logger.header("Risk checks")
    if r["risk"].get("checked"):
        for reason in r["risk"]["reasons"]:
            logger.step(f"note      : {reason}")
        logger.step(f"approved  : {r['risk']['approved']} · "
                    f"final size={r['risk']['capped_size_pct']}% · stop={r['risk']['stop_pct']}%")
    else:
        logger.step(r["risk"]["reason"])
    logger.header("Order / Result")
    if r["order"]:
        o = r["order"]
        logger.step(f"order     : {o['order_id']} {o['direction'].upper()} {o['ticker']} "
                    f"${o['notional_usd']:,.2f} @ ${o['price']} stop→${o['stop_price']}")
    logger.step(f"result    : {r['result']}")
    logger.divider()
