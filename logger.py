"""Explainable logging: human console lines + machine JSONL record per run.

Console output is ASCII-safe (a redirected Windows console uses cp1252 and
crashes on arrows/emoji), so step()/header()/divider() transliterate common
non-ASCII chars to ASCII equivalents before printing.
"""
from __future__ import annotations
import datetime as dt
import json
from pathlib import Path
from typing import Any

import config

_REPLACEMENTS = {
    "→": "->", "←": "<-", "≈": "~", "·": "-", "—": "-", "–": "-",
    "🌙": "moon", "⛔": "x", "✅": "ok", "❌": "x", "≥": ">=", "≤": "<=",
}


def _ascii(msg: str) -> str:
    """Make a string safe for any console encoding (cp1252 etc.)."""
    for k, v in _REPLACEMENTS.items():
        msg = msg.replace(k, v)
    return msg.encode("ascii", "replace").decode("ascii")


def utc_now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def _log_file() -> Path:
    config.LOG_DIR.mkdir(parents=True, exist_ok=True)
    day = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")
    return config.LOG_DIR / f"agent-{day}.jsonl"


def log_run(record: dict[str, Any]) -> Path:
    """Append one full run record (event->decision->risk->order->result)."""
    path = _log_file()
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return path


def step(msg: str) -> None:
    print(f"  {_ascii(str(msg))}")


def header(title: str) -> None:
    print(f"\n=== {_ascii(title)} ===")


def divider() -> None:
    print("-" * 64)
