"""Paper broker: Agent-Hub-style account simulator. NO real execution.

Ledger in state/: orders, positions, market, daily.
Mark-to-market: day P&L = (realized_today + unrealized_open) / day_start_equity.
refresh_day_pnl() re-marks the book and trips the daily-loss halt when breached —
agent.py calls it on every run, so the halt fires from live usage, not just tests.
"""
from __future__ import annotations
import datetime as dt
import json
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path

import config

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

    def __init__(self, equity: float, state_dir: Path | str | None = None) -> None:
        self.equity = equity
        # state_dir override exists so tests can use a temp ledger
        # instead of polluting the demo's real state/.
        self.state_dir = Path(state_dir) if state_dir else config.STATE_DIR
        self.state_dir.mkdir(parents=True, exist_ok=True)

    # -- positions / market --------------------------------------------------
    def positions_list(self) -> list[dict]:
        return _load(self.state_dir / "positions.json", [])

    def open_position_count(self) -> int:
        return len(self.positions_list())

    def open_tickers(self) -> list[str]:
        return [str(p.get("ticker", "")) for p in self.positions_list()]

    def get_market_price(self, ticker: str) -> float:
        """Current paper mark: override in market.json, else REF_PRICES fill."""
        ticker = ticker.upper().strip()
        market = _load(self.state_dir / "market.json", {})
        if ticker in market:
            return float(market[ticker])
        if ticker in REF_PRICES:
            return REF_PRICES[ticker]
        raise ValueError(f"Unknown rToken ticker: {ticker}")

    def set_market_price(self, ticker: str, price: float) -> float:
        """Simulate a market move (demo / test hook). Re-marks the book."""
        ticker = ticker.upper().strip()
        if ticker not in config.ALLOWED_TICKERS:
            raise ValueError(f"Unknown rToken ticker: {ticker}")
        if not price or price <= 0:
            raise ValueError("price must be > 0")
        market = _load(self.state_dir / "market.json", {})
        market[ticker] = float(price)
        _save(self.state_dir / "market.json", market)
        self.refresh_day_pnl()  # a shock can trip the halt immediately
        return float(price)

    # -- P&L (mark-to-market) --------------------------------------------------
    @staticmethod
    def _position_pnl_usd(pos: dict, mark: float) -> float:
        sign = 1.0 if pos.get("direction") == "long" else -1.0
        return sign * (mark - float(pos.get("price", 0.0))) * float(pos.get("qty", 0.0))

    def unrealized_pnl_usd(self) -> float:
        total = 0.0
        for pos in self.positions_list():
            total += self._position_pnl_usd(pos, self.get_market_price(pos["ticker"]))
        return round(total, 2)

    def _day_entry(self) -> dict:
        today = dt.date.today().isoformat()
        daily = _load(self.state_dir / "daily.json", {})
        entry = daily.get(today)
        if not isinstance(entry, dict):
            # First touch of the day pins the baseline equity the % is measured on.
            entry = {"start_equity": self.equity, "realized_pnl_usd": 0.0,
                     "pnl_pct": 0.0, "halted": False}
            daily[today] = entry
            _save(self.state_dir / "daily.json", daily)
        return entry

    def _save_day_entry(self, entry: dict) -> None:
        today = dt.date.today().isoformat()
        daily = _load(self.state_dir / "daily.json", {})
        daily[today] = entry
        _save(self.state_dir / "daily.json", daily)

    def refresh_day_pnl(self) -> float:
        """Re-mark the book, persist day P&L %, and trip the halt if breached.

        Called by agent.py on every run (and by --status), so the daily-loss
        rule fires from live usage — not just hand-built unit tests.
        """
        entry = self._day_entry()
        base = float(entry.get("start_equity") or self.equity)
        pct = round((float(entry.get("realized_pnl_usd", 0.0))
                     + self.unrealized_pnl_usd()) / base * 100, 4)
        entry["pnl_pct"] = pct
        if pct <= -config.DAILY_LOSS_LIMIT_PCT and not entry.get("halted"):
            entry["halted"] = True
            entry["halt_reason"] = (
                f"Day P&L {pct:.2f}% breached -{config.DAILY_LOSS_LIMIT_PCT}% limit."
            )
        self._save_day_entry(entry)
        return pct

    def day_pnl_pct(self) -> float:
        return self.refresh_day_pnl()

    def is_halted(self) -> bool:
        self.refresh_day_pnl()  # keep the flag current with live marks
        return bool(self._day_entry().get("halted", False))

    def trip_halt(self, day_pnl_pct: float) -> None:
        entry = self._day_entry()
        entry.update({"pnl_pct": float(day_pnl_pct), "halted": True})
        self._save_day_entry(entry)

    # -- execution ----------------------------------------------------------
    def place_order(self, ticker: str, direction: str, size_pct: float) -> PaperOrder:
        """Simulate a paper fill AFTER risk approval. Attaches 5% hard stop."""
        ticker = ticker.upper().strip()
        if ticker not in config.ALLOWED_TICKERS:
            raise ValueError(f"Unknown rToken ticker: {ticker}")
        if direction not in ("long", "short"):
            raise ValueError("direction must be 'long' or 'short'")

        price = self.get_market_price(ticker)  # current mark, not a stale constant
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

    # -- closes (realize P&L) ----------------------------------------------------
    def close_position(self, order_id: str) -> dict:
        """Close one paper position at the current mark; books realized P&L."""
        keep, closed = [], None
        for pos in self.positions_list():
            if pos.get("order_id") == order_id and closed is None:
                closed = pos
            else:
                keep.append(pos)
        if closed is None:
            raise ValueError(f"No open position: {order_id}")
        mark = self.get_market_price(closed["ticker"])
        pnl = round(self._position_pnl_usd(closed, mark), 2)
        _save(self.state_dir / "positions.json", keep)
        entry = self._day_entry()
        entry["realized_pnl_usd"] = round(float(entry.get("realized_pnl_usd", 0.0)) + pnl, 2)
        self._save_day_entry(entry)
        orders = _load(self.state_dir / "orders.json", [])
        orders.append({"order_id": closed["order_id"], "ticker": closed["ticker"],
                       "direction": closed["direction"], "close_price": mark,
                       "realized_pnl_usd": pnl, "status": "CLOSED (paper)",
                       "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")})
        _save(self.state_dir / "orders.json", orders)
        self.refresh_day_pnl()  # a realized loss can trip the halt immediately
        return {"order_id": closed["order_id"], "ticker": closed["ticker"],
                "direction": closed["direction"], "close_price": mark,
                "realized_pnl_usd": pnl}

    def close_all(self) -> list[dict]:
        return [self.close_position(p["order_id"]) for p in self.positions_list()]

    def reset_demo_state(self) -> None:
        for name in ("orders.json", "positions.json", "daily.json", "market.json"):
            p = self.state_dir / name
            if p.exists():
                p.unlink()
