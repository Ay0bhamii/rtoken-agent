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
    day_pnl_pct: float                 # today's P&L (realized + unrealized MtM) in %
    open_positions: int                # count of open paper positions
    halted: bool = False               # set when daily-loss halt tripped
    # Same-ticker guard: agent passes the candidate ticker + open tickers so the
    # gate can block a conflicting/duplicate position on the same name (fix #2).
    ticker: str = ""                   # candidate ticker, e.g. "NVDA"
    direction: str = ""                # candidate direction: "long" | "short"
    open_tickers: tuple[str, ...] = ()           # tickers already held
    open_exposure: tuple[tuple[str, str], ...] = ()  # (ticker, direction) held


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
    # Fix #2: no second position on the same ticker. Simultaneous long+short
    # on one name nets to noise while consuming a risk slot, so the default
    # policy blocks ANY duplicate ticker (same or opposite direction).
    # Set ALLOW_SAME_TICKER_ADD = True in config to relax to opposite-only blocks.
    candidate = (state.ticker or "").upper()
    if candidate and candidate in [t.upper() for t in state.open_tickers]:
        held = [d for (t, d) in state.open_exposure if t.upper() == candidate]
        held_txt = f" (holding {', '.join(held)})" if held else ""
        if getattr(config, "ALLOW_SAME_TICKER_ADD", False):
            if state.direction and state.direction in held:
                reasons.append(
                    f"REJECT: already {state.direction} {candidate}{held_txt} → "
                    f"adding to the same side is blocked."
                )
        else:
            reasons.append(
                f"REJECT: already hold {candidate}{held_txt} → one position "
                f"per ticker (close it first, or enable ALLOW_SAME_TICKER_ADD)."
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
    # Fix #5: the old `reasons=[] if approved and capped == requested...` line was
    # dead logic (that branch was already empty whenever it fired). Keep exactly
    # the notes that matter: nothing when clean, all notes when capped/approved.
    kept = [] if (approved and not reasons) else reasons
    return RiskVerdict(
        approved=approved,
        reasons=kept,
        capped_size_pct=capped if approved else 0.0,
    )
