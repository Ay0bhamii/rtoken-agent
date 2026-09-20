# rToken Event-Driven Trading Agent (paper-only demo)

Minimal but serious **event-driven paper-trading agent** for tokenized US stocks (rTokens).

> Safety first: this is **PAPER TRADING ONLY**. No real orders, no real money.
> Explainability over sophistication: every run logs
> `timestamp → event → interpretation → decision → risk checks → order → result`.

## Core flow (as requested)

1. **Fetch** latest macro / geopolitical / policy news
   (`news.py` → tries `bitget-signal` skill adapter first, falls back to RSS/sample data)
2. **LLM decides**: does this event meaningfully affect major US stocks / rTokens
   this weekend or after-hours? (`llm.py`)
3. If yes → structured signal:
   `ticker, direction (long/short), position size (% of capital), confidence, reasoning`
4. **Hard risk rules** applied *before* any order (`risk.py`):
   - Position size ≤ **12%** of capital
   - Daily loss limit **2.5%** → halt trading for the day
   - Max **2** open positions
   - Hard stop **5%** per position
5. **Paper order** via Agent Hub / Agentic-style account (`broker.py` — simulated fill, local ledger)
6. **Log everything** clearly (`logger.py` → console + JSONL in `logs/`)

## Quick start (Windows PowerShell, Python 3.10+ — stdlib only, no pip install needed)

```powershell
cd c:\Users\GKL\nimiq-hack-lab
python -m rtoken_agent.cli --list-samples
python -m rtoken_agent.cli --reset-state
python -m rtoken_agent.cli --sample 1     # dovish surprise  → LONG NVDA paper order
python -m rtoken_agent.cli --sample 2     # chip curbs       → SHORT NVDA paper order
python -m rtoken_agent.cli --sample 5     # pie contest      → NO_TRADE (flat)
python -m rtoken_agent.cli --sample 6     # 3rd position     → BLOCKED by risk gate
python -m rtoken_agent.cli --event "Fed emergency weekend rate cut, dovish surprise"
python -m rtoken_agent.cli --news --dry-run   # live fetch, no orders
python -m rtoken_agent.cli --status
python -m rtoken_agent.test_agent         # 8 smoke tests (risk/interpreter/broker)
```

Sample events live in `samples.json` (weekend / after-hours scenarios).

## Files

| File | Purpose |
|---|---|
| `cli.py` | Runnable demo CLI (input or load sample event, see full flow) |
| `agent.py` | Orchestrator: news → LLM → risk → broker → log |
| `news.py` | News adapters: `bitget-signal` skill hook + RSS + samples |
| `llm.py` | LLM interpreter (OpenAI-compatible via stdlib `urllib`, else transparent rule fallback) |
| `risk.py` | Hard risk gate (pure function, unit-testable) |
| `broker.py` | Paper Agent-Hub broker: positions, stops, daily P&L ledger |
| `logger.py` | JSONL + console logging, one record per run |
| `config.py` | Risk limits, capital, tickers, paths |
| `samples.json` | Sample weekend events for the demo |
| `test_agent.py` | Smoke tests (stdlib unittest, no dependency) |
| `state/` | Local paper ledger (`orders.json`, `positions.json`, `daily.json`) |
| `logs/` | Append-only run logs (`agent-YYYY-MM-DD.jsonl`) |

## Plugging in real pieces later

- **Real news skill**: implement `fetch_bitget_signal_news()` in `news.py`
  (currently a documented stub — drops in where the RSS fallback is).
- **Real LLM**: set `OPENAI_API_KEY` (and optionally `OPENAI_BASE_URL`, `OPENAI_MODEL`).
  Without a key the agent uses a clearly-labelled keyword fallback so the demo
  always runs offline.
- **Real Agent Hub execution**: replace `PaperBroker.place_order()` internals;
  keep calling it *after* `risk.check()` — never bypass the gate.

## Risk rules (enforced in code, not just docs)

```text
MAX_POSITION_PCT   = 12.0   # any single position ≤ 12% of equity
DAILY_LOSS_LIMIT   = 2.5    # day P&L ≤ -2.5% → HALT (no new orders)
MAX_OPEN_POSITIONS = 2      # third signal is rejected while 2 are open
STOP_LOSS_PCT      = 5.0    # every paper order carries a 5% hard stop
```

Risk rejections are logged with reasons — a rejected trade is a *successful* safety outcome.
