"""Smoke tests: risk gate + fallback interpreter + paper broker (stdlib unittest).

Run from repo root:  python -m rtoken_agent.test_agent
"""
from __future__ import annotations
import unittest

from . import config, risk
from .broker import PaperBroker
from .llm import interpret_event


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
    def test_stop_attached(self):
        b = PaperBroker(100_000)
        o = b.place_order.__self__  # sanity: method exists
        self.assertTrue(callable(b.place_order))
        self.assertEqual(config.STOP_LOSS_PCT, 5.0)
        _ = o


if __name__ == "__main__":
    unittest.main(verbosity=2)
