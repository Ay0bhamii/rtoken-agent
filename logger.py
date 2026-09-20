"""Explainable logging: human console lines + machine JSONL record per run."""
from __future__ import annotations
import datetime as dt
import json
from pathlib import Path
from typing import Any

from . import config


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
    print(f"  {msg}")


def header(title: str) -> None:
    print(f"\n=== {title} ===")


def divider() -> None:
    print("-" * 64)
