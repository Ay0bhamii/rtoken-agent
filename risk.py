"""Hard risk gate. Pure function: easy to test, impossible to bypass accidentally.

agent.py MUST call check() before broker.place_order(). A rejection is a
successful safety outcome and is logged with explicit reasons.
"""
from __future__ import annotations
from dataclasses import dataclass, field

import config


@dataclass
class RiskState:
    equity: float                      # current paper equity (USD)
    day_pnl_pct: float                 # today's realised P&L in % of start equity
    open_positions: int                # count of open paper positions
    halted: bool = False               # set when daily-loss halt tripped


@dataclass
class RiskVerdict:
    approved: bool
    reasons: list[str] = field(default_factory=list)  # empty when approved
    capped_size_pct: float = 0.0       # size after 12% cap is applied
    stop_pct: float = config.STOP_LOSS_PCT


def check(requested_size_pct: float, state: RiskState) -> RiskVerdict:
    """Apply the four hard rules. Never raises on bad input — rejects instead."""
    reasons: list[str] = []

    if state.halted or state.day_pnl_pct <= -config.DAILY_LOSS_LIMIT_PCT:
        reasons.append(
            f"HALT: daily loss {state.day_pnl_pct:.2f}% breached "
            f"limit -{config.DAILY_LOSS_LIMIT_PCT}% → no new orders today."
        )
    if state.open_positions >= config.MAX_OPEN_POSITIONS:
        reasons.append(
            f"REJECT: {state.open_positions} open positions "
            f"(max {config.MAX_OPEN_POSITIONS}). Close one first."
        )
    if not (0 < requested_size_pct <= 100):
        reasons.append(f"REJECT: invalid size {requested_size_pct} (must be 0-100%).")
        capped = 0.0
    else:
        capped = min(requested_size_pct, config.MAX_POSITION_PCT)
        if requested_size_pct > config.MAX_POSITION_PCT:
            # Cap is applied but the trim is surfaced for explainability.
            reasons.append(
                f"CAPPED: requested {requested_size_pct:.1f}% > "
                f"max {config.MAX_POSITION_PCT}% → trimmed to {capped:.1f}%."
            )

    # A "CAPPED" note alone must not block the trade; HALT/REJECT/invalid do.
    blocking = [r for r in reasons if not r.startswith("CAPPED")]
    approved = not blocking
    return RiskVerdict(
        approved=approved,
        reasons=[] if approved and capped == requested_size_pct else reasons,
        capped_size_pct=capped if approved else 0.0,
    )
