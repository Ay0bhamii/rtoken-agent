"""Central configuration + hard risk limits. Single source of truth."""
from __future__ import annotations
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
STATE_DIR = BASE_DIR / "state"
LOG_DIR = BASE_DIR / "logs"
SAMPLES_FILE = BASE_DIR / "samples.json"

# ---- Paper portfolio ----
DEFAULT_CAPITAL = float(os.getenv("RTOKEN_CAPITAL", "100000.0"))  # USD paper equity

# ---- HARD RISK RULES (do not loosen without review) ----
MAX_POSITION_PCT = 12.0    # single position notional <= 12% of equity
DAILY_LOSS_LIMIT_PCT = 2.5  # day P&L <= -2.5%  -> HALT (no new orders)
MAX_OPEN_POSITIONS = 2      # at most 2 open positions
STOP_LOSS_PCT = 5.0         # every order carries a 5% hard stop

# ---- Tradeable rToken universe (tokenized US majors, demo mapping) ----
# The agent may only emit these tickers, so every signal is paper-tradeable.
ALLOWED_TICKERS = ["AAPL", "MSFT", "NVDA", "TSLA", "AMZN", "META", "GOOGL", "AMD"]

# ---- Exposure policy ----
# Default False = one position per ticker (blocks long+short on the same name,
# which would net to noise while consuming a risk slot). Set True to allow
# adding, while still blocking same-side doubles.
ALLOW_SAME_TICKER_ADD = False

# ---- LLM (optional; offline fallback when unset) ----
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

# ---- News ----
NEWS_RSS_URLS = [
    # Macro / policy feeds. Any failure -> graceful fallback to samples.
    "https://feeds.bloomberg.com/markets/news.rss",
    "https://www.federalreserve.gov/feeds/press_all.xml",
]
NEWS_TIMEOUT_S = 8
