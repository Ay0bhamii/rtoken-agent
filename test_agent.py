"""Smoke tests: risk gate + fallback interpreter + paper broker (stdlib unittest).

Run:  python test_agent.py   or   python -m test_agent
"""
from __future__ import annotations
import tempfile
import unittest
from pathlib import Path

import config
import risk
from broker import PaperBroker, REF_PRICES
from llm import interpret_event


def _test_broker(equity: float = 100_000.0) -> PaperBroker:
    # Isolated temp ledger: tests never touch the demo's real state/.
    return PaperBroker(equity, state_dir=Path(tempfile.mkdtemp(prefix="rtoken-test-")))


class TestRiskGate(unittest.TestCase):
    def test_position_cap_trims_to_12(self):
        v = risk.check(99.0, risk.RiskState(100_000, 0.0, 0))
        self.assertTrue(v.approved)
        self.assertEqual(v.capped_size_pct, config.MAX_POSITION_PCT)

    def test_daily_loss_halts(self):
        v = risk.check(5.0, risk.RiskState(100_000, -3.0, 0))
        self.assertFalse(v.approved)
        self.assertTrue(any("HALT" in r for r in v.reasons))

    def test_max_two_positions(self):
        v = risk.check(5.0, risk.RiskState(100_000, 0.0, 2))
        self.assertFalse(v.approved)

    def test_same_ticker_blocked(self):
        # Fix #2: no long+short (or double) on the same name by default.
        st = risk.RiskState(100_000, 0.0, 1, ticker="NVDA", direction="short",
                            open_tickers=("NVDA",), open_exposure=(("NVDA", "long"),))
        v = risk.check(5.0, st)
        self.assertFalse(v.approved)
        self.assertTrue(any("NVDA" in r for r in v.reasons))

    def test_invalid_size_rejected(self):
        self.assertFalse(risk.check(0, risk.RiskState(100_000, 0.0, 0)).approved)


class TestInterpreter(unittest.TestCase):
    def test_dovish_maps_to_long(self):
        s = interpret_event("Fed emergency weekend rate cut, dovish surprise")
        self.assertTrue(s.trade and s.direction == "long")

    def test_irrelevant_event_stays_flat(self):
        s = interpret_event("Local bakery wins weekend pie contest downtown")
        self.assertFalse(s.trade)

    def test_engine_is_labelled(self):
        s = interpret_event("anything")
        self.assertIn(s.engine, ("rules-fallback", "llm", "llm-error-fallback"))


class TestBroker(unittest.TestCase):
    def test_stop_math_long_and_short(self):
        # Fix #4: actually place orders and assert the 5% stop-price math.
        b = _test_broker()
        long_o = b.place_order("NVDA", "long", 6.0)
        short_o = b.place_order("MSFT", "short", 5.0)
        self.assertEqual(long_o.stop_pct, config.STOP_LOSS_PCT)
        self.assertAlmostEqual(long_o.stop_price,
                               round(REF_PRICES["NVDA"] * 0.95, 2))
        self.assertAlmostEqual(short_o.stop_price,
                               round(REF_PRICES["MSFT"] * 1.05, 2))
        self.assertAlmostEqual(long_o.notional_usd, 100_000 * 6.0 / 100, places=2)
        self.assertEqual(b.open_position_count(), 2)

    def test_live_halt_wiring(self):
        # Fix #1: the halt must fire from LIVE marks — no hand-built RiskState.
        # Two 12%-of-equity longs fully adverse (-5% each) ≈ -1.2% day P&L...
        # so push NVDA down ~25%: 12% * 25% ≈ -3% → past the -2.5% halt.
        b = _test_broker()
        b.place_order("NVDA", "long", 12.0)
        self.assertFalse(b.is_halted())
        b.set_market_price("NVDA", round(REF_PRICES["NVDA"] * 0.75, 2))
        self.assertLess(b.day_pnl_pct(), -config.DAILY_LOSS_LIMIT_PCT)
        self.assertTrue(b.is_halted())
        # ...and the gate itself must then refuse new risk.
        v = risk.check(5.0, risk.RiskState(100_000, b.day_pnl_pct(), 1,
                                           halted=b.is_halted()))
        self.assertFalse(v.approved)
        self.assertTrue(any("HALT" in r for r in v.reasons))

    def test_close_realizes_pnl(self):
        b = _test_broker()
        o = b.place_order("NVDA", "long", 6.0)
        b.set_market_price("NVDA", round(REF_PRICES["NVDA"] * 1.10, 2))  # +10%
        c = b.close_position(o.order_id)
        self.assertGreater(c["realized_pnl_usd"], 0)
        self.assertEqual(b.open_position_count(), 0)
        self.assertGreater(b.day_pnl_pct(), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
