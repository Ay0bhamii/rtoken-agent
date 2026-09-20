"""Paper broker: Agent-Hub-style account simulator. NO real execution.

Keeps a local ledger in state/: orders, positions, daily P&L.
Every order carries the 5% hard stop; fills are simulated at a reference
price so the demo is deterministic and safe.
"""
from __future__ import annotations
import datetime as dt
import json
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path

from . import config

# Demo reference prices (paper fills). Replace with live rToken quotes later.
REF_PRICES = {
    "AAPL": 232.0, "MSFT": 428.0, "NVDA": 131.0, "TSLA": 248.0,
    "AMZN": 197.0, "META": 563.0, "GOOGL": 176.0, "AMD": 122.0,
}


@dataclass
class PaperOrder:
    order_id: str
    timestamp: str
    ticker: str
    direction: str          # "long" | "short"
    size_pct: float         # of equity, post risk-cap
    notional_usd: float
    price: float
    stop_pct: float
    stop_price: float
    status: str = "FILLED (paper)"


def _load(path: Path, default):
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return default
    return default


def _save(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


class PaperBroker:
    """Minimal Agent-Hub-like paper account."""

    def __init__(self, equity: float) -> None:
        self.equity = equity
        self.state_dir = config.STATE_DIR
        self.state_dir.mkdir(parents=True, exist_ok=True)

    # -- state helpers -----------------------------------------------------
    def open_position_count(self) -> int:
        return len(_load(self.state_dir / "positions.json", []))

    def day_pnl_pct(self) -> float:
        today = dt.date.today().isoformat()
        daily = _load(self.state_dir / "daily.json", {})
        return float(daily.get(today, {}).get("pnl_pct", 0.0))

    def is_halted(self) -> bool:
        today = dt.date.today().isoformat()
        daily = _load(self.state_dir / "daily.json", {})
        return bool(daily.get(today, {}).get("halted", False))

    def trip_halt(self, day_pnl_pct: float) -> None:
        today = dt.date.today().isoformat()
        daily = _load(self.state_dir / "daily.json", {})
        daily[today] = {"pnl_pct": day_pnl_pct, "halted": True}
        _save(self.state_dir / "daily.json", daily)

    # -- execution ----------------------------------------------------------
    def place_order(self, ticker: str, direction: str, size_pct: float) -> PaperOrder:
        """Simulate a paper fill AFTER risk approval. Attaches 5% hard stop."""
        ticker = ticker.upper().strip()
        if ticker not in config.ALLOWED_TICKERS:
            raise ValueError(f"Unknown rToken ticker: {ticker}")
        if direction not in ("long", "short"):
            raise ValueError("direction must be 'long' or 'short'")

        price = REF_PRICES[ticker]
        notional = round(self.equity * size_pct / 100.0, 2)
        stop = config.STOP_LOSS_PCT
        stop_price = round(price * (1 - stop / 100) if direction == "long"
                           else price * (1 + stop / 100), 2)
        order = PaperOrder(
            order_id="paper-" + uuid.uuid4().hex[:8],
            timestamp=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
            ticker=ticker, direction=direction, size_pct=size_pct,
            notional_usd=notional, price=price,
            stop_pct=stop, stop_price=stop_price,
        )
        orders = _load(self.state_dir / "orders.json", [])
        orders.append(asdict(order))
        _save(self.state_dir / "orders.json", orders)

        positions = _load(self.state_dir / "positions.json", [])
        positions.append({**asdict(order), "qty": round(notional / price, 4)})
        _save(self.state_dir / "positions.json", positions)
        return order

    def reset_demo_state(self) -> None:
        for name in ("orders.json", "positions.json", "daily.json"):
            p = self.state_dir / name
            if p.exists():
                p.unlink()
