# 🌙 NightShift Agent — Event-Driven Trading for 7×24 rTokens

> **Built for Bitget AI Base Camp Hackathon S2 – Agentic Trading / Event-Driven Agent**
>
> An explainable, risk-gated paper-trading agent for Bitget rTokens — every trade
> decision is logged with its full reasoning chain, every order is capped and
> stopped by a hard-coded risk gate that cannot be bypassed, and fills use
> Bitget's public market API where available (`--live`).
>
> **Paper trading only – no real funds at risk.**
> Promotional post: _link coming soon — will be added here once published._

## Thesis

US equities sleep on weekends. Tokenized US stocks (rTokens) do not — and neither
do macro shocks, wars, or policy surprises. Retail traders go offline; risk does not.
**NightShift Agent is the night shift**: it watches weekend/after-hours news, acts
only when the impact on major US names is clear, and trades rTokens under
non-negotiable risk limits. When in doubt, it stays flat — and logs exactly why.

**Target user**: retail swing traders ($10k–$50k) who want weekend event exposure
without staying up all night watching headlines.

## Web dashboard (the way to demo this)

```bash
python dashboard.py --open     # → http://localhost:8080
```

One page, real pipeline: STATUS / LATEST EVENT / **AGENT BRAIN** (LLM
interpretation with engine badge) / **RISK GATE** (green APPROVED, red RISK
REJECTION) / PAPER LEDGER (positions with entry→mark, uPnL) / RUN LOG
(last 8 runs). Buttons run the exact judge sequence, plus "-3% → HALT" and
"Live news". The `live Bitget quotes` checkbox fills from `R{T}USDT` quotes
(order tagged `[bitget-live:SYMBOL]`). Everything is the real modules —
the dashboard is a window on `agent.run_event()`, not a mock.

## Deploying (Render free tier — cold starts)

The dashboard deploys as-is: Render start command is just `python dashboard.py`.
The server binds `0.0.0.0:$PORT` (Render sets `PORT`; override locally with
`--port`). Note: on Render the paper ledger is ephemeral per instance, so run
your demo within one warm session (or upgrade the disk) — fine for a demo.

Free instances sleep and take ~30–60s to wake. **Before you present**, run this
waiter — it loops until `/api/status` actually answers 200:

```bash
until curl -sf https://YOUR-APP.onrender.com/api/status > /dev/null; do echo "waking up..."; sleep 3; done; echo "LIVE ✅"
```

Want more than "the server responds" — proof the trading pipeline itself works
post-deploy? This waiter only succeeds once a sample run returns a real trade
decision (`tr` field = a signal, not just a 200):

```bash
until curl -sf -X POST https://YOUR-APP.onrender.com/api/run -H "Content-Type: application/json" -d '{"sample":1,"live":false}' | grep -q '"tr"'; do echo "waking up..."; sleep 3; done; echo "LIVE — sample 1 fired a real signal ✅"
```

Swap in your real `.onrender.com` URL once Render assigns it.

## For Judges – Quick Demo (60 seconds)

```bash
python cli.py --reset-state
python cli.py --sample 1   # dovish surprise  → LONG NVDA (fills)
python cli.py --sample 5   # pie contest      → NO_TRADE (stays flat on irrelevant news)
python cli.py --sample 3   # oil shock        → LONG TSLA (fills 2nd slot)
python cli.py --sample 6   # AI capex deal    → BLOCKED by max 2 positions
python cli.py --status     # SUMMARY: 2 open · P&L · TRADING/HALTED
```

Every run prints the full explainable flow
(event → interpretation → decision → risk checks → order/result)
and appends it as one JSON record to `logs/agent-YYYY-MM-DD.jsonl`.

Safety rails on demand:

```bash
python cli.py --simulate-loss 3.0   # books -3% realized → HALTED immediately
python cli.py --sample 4            # any new signal now refused with HALT reason
python cli.py --live --sample 1     # fill from Bitget public quote (RNVDAUSDT)
```

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
python cli.py --list-samples
python cli.py --reset-state
python cli.py --sample 1     # dovish surprise  → LONG NVDA paper order
python cli.py --sample 2     # chip curbs       → SHORT NVDA, but BLOCKED (already hold NVDA)
python cli.py --sample 5     # pie contest      → NO_TRADE (flat)
python cli.py --sample 3     # oil shock        → LONG TSLA (fills 2nd slot)
python cli.py --sample 6     # AI capex         → BLOCKED by max 2 positions
python cli.py --mark NVDA 98.25   # adverse shock → live P&L drops, can trip -2.5% HALT
python cli.py --simulate-loss 3.0  # one-command halt demo: books -3% → HALTED
python cli.py --live --sample 1    # fill from Bitget public quote when available
python cli.py --status       # open positions, live day P&L, halted or not
python test_agent.py         # 12 tests (risk gate / halt wiring / stops / closes / live)
```

Sample events live in `samples.json` (weekend / after-hours scenarios).

# Demo evidence (for judges)

Screen recording (60–90s, running the Quick Demo above):
_link coming soon (YouTube unlisted / Loom) — will be added here once uploaded._

Example log excerpts live in `logs/` after any run
(`agent-YYYY-MM-DD.jsonl` — one JSON record per run:
event → interpretation → decision → risk → order/result).

## Files

| File | Purpose |
|---|---|
| `cli.py` | Runnable demo CLI (input or load sample event, see full flow) |
| `dashboard.py` + `dash_top.html`/`dash_js.html` | **Live web dashboard** (stdlib `http.server`, auto-refresh, one-click demo buttons) |
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

## Plugging in the real Bitget stack

- **bitget-signal (news/macro)**: implement `fetch_bitget_signal_news()` in
  `news.py` (currently a documented stub). Priority is
  skill → RSS → bundled samples, so the demo always runs.
- **Real LLM**: set `OPENAI_API_KEY` (and optionally `OPENAI_BASE_URL`,
  `OPENAI_MODEL`). Without a key the agent uses the clearly-labelled
  `rules-fallback` engine (see `llm.py`) — logs never confuse it with an LLM call.
- **Bitget Agent Hub / Agentic account (execution)**: replace
  `PaperBroker.place_order()` internals; keep calling it *after*
  `risk.check()` — the gate is deliberately placed before any broker call so
  it can never be bypassed when real execution is added.
- **Bitget public market data**: `broker.fetch_bitget_price()` pulls no-key spot
  quotes (`api.bitget.com/api/v2/spot/market/tickers`, trying `R{T}USDT` first —
  verified live: `RNVDAUSDT` resolves — then `{T}USDT`); pass `--live` to fill
  from it. Every order is tagged `[bitget-live:SYMBOL]` or `[static-fallback]`
  so logs never pretend.

## Risk rules (enforced in code, not just docs)

```text
MAX_POSITION_PCT   = 12.0   # any single position ≤ 12% of equity
DAILY_LOSS_LIMIT   = 2.5    # day P&L ≤ -2.5% → HALT (no new orders)
MAX_OPEN_POSITIONS = 2      # third signal is rejected while 2 are open
STOP_LOSS_PCT      = 5.0    # every paper order carries a 5% hard stop
```

Risk rejections are logged with reasons — a rejected trade is a *successful* safety outcome.
