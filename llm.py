"""LLM interpreter: step 2-3 of the core flow.

Decides: does this event meaningfully affect major US stocks / rTokens this
weekend or after-hours? If yes → ticker, direction, size %, confidence, reasoning.

- With OPENAI_API_KEY set: calls an OpenAI-compatible chat API via stdlib
  urllib (no extra dependency), asks for strict JSON.
- Without a key: transparent RULE-BASED fallback using sector keywords.
  The fallback always reports engine="rules-fallback" so logs never
  pretend to be an LLM. It is deliberately conservative: unknown events
  → NO_TRADE rather than a guess.
"""
from __future__ import annotations
import json
import re
import urllib.request
from dataclasses import dataclass

from . import config

SYSTEM_PROMPT = (
    "You are a cautious event-driven equity analyst for tokenized US stocks (rTokens). "
    "Given ONE weekend/after-hours macro, geopolitical, or policy event, decide if it "
    "meaningfully affects major US stocks. Respond with STRICT JSON only: "
    '{"trade": true/false, "ticker": "AAPL|MSFT|NVDA|TSLA|AMZN|META|GOOGL|AMD|null", '
    '"direction": "long|short|null", "size_pct": number|null (suggested 2-12), '
    '"confidence": 0-1, "reasoning": "one or two sentences"}. '
    "If impact is unclear or indirect, set trade=false and nulls. Never exceed 12% size."
)

# Conservative keyword map for the offline fallback: (label, pattern, tickers, direction, size).
_FALLBACK_RULES: list[tuple[str, str, list[str], str, float]] = [
    ("dovish / rate-cut talk", r"\brate cut\b|\brate cuts\b|emergency cut|dovish|\bstimulus\b|\beasing\b", ["NVDA", "MSFT"], "long", 6.0),
    ("hawkish / hot inflation", r"\brate hike\b|\brate hikes\b|hawkish|hot cpi|hot inflation", ["NVDA", "MSFT"], "short", 5.0),
    ("oil shock / geopolitical escalation", r"oil shock|oil spike|opec cut|\bmissile\b|\bstrike on\b|invasion|war escalat", ["TSLA"], "long", 5.0),
    ("chip export curbs", r"export ban|chip ban|export curb|chip curb|semiconductor curb|taiwan", ["NVDA"], "short", 6.0),
    ("antitrust overhang", r"antitrust|doj sues|breakup|dma fine", ["GOOGL", "META"], "short", 5.0),
    ("AI capex deal", r"ai deal|ai contract|datacenter|gpu order", ["NVDA", "MSFT"], "long", 7.0),
    ("TSLA-specific negative", r"recall|autopilot probe|deliveries miss", ["TSLA"], "short", 5.0),
    ("cloud growth", r"cloud growth|\bazure\b|aws growth", ["MSFT", "AMZN"], "long", 5.0),
]


@dataclass
class Signal:
    trade: bool
    ticker: str | None
    direction: str | None      # "long" | "short" | None
    size_pct: float | None     # requested % of capital
    confidence: float
    reasoning: str
    engine: str                # "llm" | "rules-fallback"


def _fallback_decide(event_text: str) -> Signal:
    t = event_text.lower()
    for label, pattern, tickers, direction, size in _FALLBACK_RULES:
        if re.search(pattern, t):
            ticker = tickers[0]
            return Signal(True, ticker, direction, size, 0.55,
                          f"Offline theme match ({label}) → "
                          f"{ticker} {direction}; conservative size, verify before trusting.",
                          "rules-fallback")
    # Also catch "no real impact" weekend filler explicitly.
    return Signal(False, None, None, None, 0.35,
                  "No clear transmission channel to mega-cap rTokens this weekend; "
                  "staying flat is the safe default.", "rules-fallback")


def _llm_decide(event_text: str) -> Signal:
    payload = {"model": config.OPENAI_MODEL, "temperature": 0.2,
               "messages": [{"role": "system", "content": SYSTEM_PROMPT},
                            {"role": "user", "content": event_text[:2000]}]}
    req = urllib.request.Request(
        config.OPENAI_BASE_URL.rstrip("/") + "/chat/completions",
        data=json.dumps(payload).encode(),
        headers={"Authorization": f"Bearer {config.OPENAI_API_KEY}",
                 "Content-Type": "application/json"},
        method="POST")
    with urllib.request.urlopen(req, timeout=25) as resp:
        data = json.loads(resp.read().decode())
    content = data["choices"][0]["message"]["content"]
    parsed = json.loads(content[content.index("{"):content.rindex("}") + 1])
    ticker = (parsed.get("ticker") or None)
    if ticker:
        ticker = str(ticker).upper()
        if ticker not in config.ALLOWED_TICKERS:
            ticker = None
    direction = parsed.get("direction")
    if direction not in ("long", "short"):
        direction = None
    size = parsed.get("size_pct")
    size = float(size) if isinstance(size, (int, float)) else None
    trade = bool(parsed.get("trade")) and ticker and direction
    return Signal(bool(trade), ticker if trade else None, direction if trade else None,
                  size if trade else None, float(parsed.get("confidence", 0.5)),
                  str(parsed.get("reasoning", "")), "llm")


def interpret_event(event_text: str) -> Signal:
    """Entry point. LLM when configured, else labelled fallback. Never raises."""
    try:
        if config.OPENAI_API_KEY:
            return _llm_decide(event_text)
    except Exception as exc:  # LLM failure must degrade to flat, loudly
        return Signal(False, None, None, None, 0.2,
                      f"LLM call failed ({exc}); defaulting to NO_TRADE for safety.",
                      "llm-error-fallback")
    return _fallback_decide(event_text)
