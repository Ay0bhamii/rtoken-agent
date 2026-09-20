#!/usr/bin/env python3
"""Runnable demo CLI: input or load a sample weekend event, see the full flow.

Examples (PowerShell):
    python cli.py --list-samples
    python cli.py --sample 1
    python cli.py --event "Fed emergency weekend rate cut ..."
    python cli.py --news --dry-run        # fetch news, interpret, skip orders
    python cli.py --sample 3 --capital 50000
    python cli.py --reset-state           # wipe paper ledger (demo helper)

Safety: paper only. --dry-run runs interpretation + risk without placing orders.
"""
from __future__ import annotations
import argparse
import sys
from pathlib import Path

# Allow BOTH: `python -m rtoken_agent.cli` (repo root) and `python cli.py` (in folder).
try:
    from . import agent, broker, config, logger
    from .news import NewsEvent, fetch_latest_news, load_sample_events
except ImportError:  # script mode
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from rtoken_agent import agent, broker, config, logger  # noqa: E402
    from rtoken_agent.news import NewsEvent, fetch_latest_news, load_sample_events  # noqa: E402


def cmd_list_samples() -> None:
    for i, e in enumerate(load_sample_events(), 1):
        print(f"[{i}] {e.title}\n    {e.body[:110]}...")


def cmd_status(capital: float) -> None:
    b = broker.PaperBroker(capital)
    print(f"equity: ${capital:,.2f} | open positions: {b.open_position_count()}/"
          f"{config.MAX_OPEN_POSITIONS} | day P&L: {b.day_pnl_pct():.2f}% "
          f"(halt at -{config.DAILY_LOSS_LIMIT_PCT}%)")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="rToken event-driven paper trading agent")
    p.add_argument("--sample", type=int, help="run sample event N (see --list-samples)")
    p.add_argument("--event", type=str, help="custom weekend event text / headline")
    p.add_argument("--news", action="store_true", help="fetch latest news then run top story")
    p.add_argument("--news-limit", type=int, default=5)
    p.add_argument("--dry-run", action="store_true", help="interpret + risk check, no orders")
    p.add_argument("--capital", type=float, default=config.DEFAULT_CAPITAL)
    p.add_argument("--list-samples", action="store_true")
    p.add_argument("--status", action="store_true")
    p.add_argument("--reset-state", action="store_true")
    a = p.parse_args(argv)

    if a.list_samples:
        cmd_list_samples()
        return 0
    if a.status:
        cmd_status(a.capital)
        return 0
    if a.reset_state:
        broker.PaperBroker(a.capital).reset_demo_state()
        print("Paper state cleared (orders/positions/daily).")
        return 0

    origin = "manual input"
    if a.news:
        events, origin = fetch_latest_news(a.news_limit)
        if not events:
            print("No news available.")
            return 1
        print(f"Fetched {len(events)} event(s) via {origin}. Running the top story:\n")
        event = events[0]
    elif a.sample:
        samples = load_sample_events()
        if not 1 <= a.sample <= len(samples):
            print(f"--sample must be 1..{len(samples)}")
            return 1
        event = samples[a.sample - 1]
        origin = f"bundled sample #{a.sample}"
    elif a.event:
        event = NewsEvent(title=a.event[:160], source="cli-input", body=a.event)
    else:
        # Interactive fallback: paste an event.
        print("Paste a weekend event (headline + context), then Enter. "
              "Empty line runs sample #1.")
        print("Samples: ", end="")
        cmd_list_samples()
        text = input("\n> ").strip()
        if not text:
            event = load_sample_events()[0]
            origin = "bundled sample #1 (default)"
        else:
            event = NewsEvent(title=text[:160], source="cli-input", body=text)

    if a.dry_run:
        # Interpretation + risk only: temporarily disable order placement.
        from rtoken_agent import risk as risk_mod
        from rtoken_agent.llm import interpret_event
        sig = interpret_event(event.text())
        print(f"\n[DRY RUN] event: {event.title}\n"
              f"signal: trade={sig.trade} {sig.direction} {sig.ticker} "
              f"size={sig.size_pct}% conf={sig.confidence} ({sig.engine})\n"
              f"reasoning: {sig.reasoning}")
        if sig.trade:
            b = broker.PaperBroker(a.capital)
            st = risk_mod.RiskState(a.capital, b.day_pnl_pct(),
                                    b.open_position_count(), b.is_halted())
            v = risk_mod.check(float(sig.size_pct or 0), st)
            print(f"risk: approved={v.approved} reasons={v.reasons or ['clean']} "
                  f"capped={v.capped_size_pct}% stop={v.stop_pct}%")
            print("DRY RUN: no order placed.")
        logger.log_run({"timestamp": logger.utc_now_iso(), "mode": "DRY RUN",
                        "event": {"title": event.title, "news_origin": origin},
                        "decision": {"trade": sig.trade}, "result": "dry-run, no order"})
        return 0

    record = agent.run_event(event, a.capital, news_origin=origin)
    log_path = config.LOG_DIR / "*.jsonl"
    print(f"\nFull record appended to {log_path} (JSONL).")
    print("modes: PAPER ONLY — no real orders exist in this demo.")
    _ = record
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
