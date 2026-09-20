"""News layer: bitget-signal skill adapter first, RSS second, samples last.

Step 1 of the core flow: "Fetch latest macro / geopolitical / policy news
(use bitget-signal skills)". This module honours that priority order:

  1. fetch_bitget_signal_news() — hook for the bitget-signal skill.
     If the skill runtime is available it is used; otherwise a clear
     stub message explains how to wire it (see docstring below).
  2. RSS fallback (stdlib urllib + xml) for macro/policy feeds.
  3. Bundled samples so the demo ALWAYS runs offline.

Every fetcher returns a list of NewsEvent(title, source, published, body).
"""
from __future__ import annotations
import json
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass

from . import config


@dataclass
class NewsEvent:
    title: str
    source: str
    published: str = ""
    body: str = ""

    def text(self) -> str:
        return f"{self.title}\n{self.body}".strip()


# ---------------------------------------------------------------------------
# 1. bitget-signal skill adapter (priority source)
# ---------------------------------------------------------------------------
def fetch_bitget_signal_news(limit: int = 5) -> list[NewsEvent]:
    """Fetch macro/geopolitical headlines via the bitget-signal skill.

    WIRING: if your environment exposes the skill as a Python module
    (e.g. `bitget_signal` with a `fetch_macro_news()` or CLI), import and
    call it here and map results to NewsEvent. Example:

        from bitget_signal import fetch_macro_news  # skill runtime
        return [NewsEvent(title=n["title"], source="bitget-signal",
                          published=n.get("ts", ""), body=n.get("summary", ""))
                for n in fetch_macro_news(limit=limit)]

    Until wired, raises ImportError so the caller falls through to RSS/samples.
    """
    try:
        import bitget_signal  # type: ignore  # skill runtime, optional
    except ImportError as exc:
        raise ImportError("bitget-signal skill runtime not installed") from exc
    fetch = getattr(bitget_signal, "fetch_macro_news", None)
    if not callable(fetch):
        raise ImportError("bitget-signal skill has no fetch_macro_news()")
    items = fetch(limit=limit) or []
    return [NewsEvent(title=i.get("title", "Untitled"), source="bitget-signal",
                      published=i.get("ts", ""), body=i.get("summary", ""))
            for i in items]


# ---------------------------------------------------------------------------
# 2. RSS fallback (stdlib only)
# ---------------------------------------------------------------------------
def _fetch_rss(url: str, limit: int) -> list[NewsEvent]:
    req = urllib.request.Request(url, headers={"User-Agent": "rtoken-agent/0.1"})
    with urllib.request.urlopen(req, timeout=config.NEWS_TIMEOUT_S) as resp:
        root = ET.fromstring(resp.read())
    out: list[NewsEvent] = []
    for item in root.iter("item"):
        title = (item.findtext("title") or "Untitled").strip()
        pub = (item.findtext("pubDate") or item.findtext("published") or "").strip()
        desc = (item.findtext("description") or "").strip()[:500]
        out.append(NewsEvent(title=title, source=url, published=pub, body=desc))
        if len(out) >= limit:
            break
    return out


def fetch_rss_news(limit: int = 5) -> list[NewsEvent]:
    events: list[NewsEvent] = []
    for url in config.NEWS_RSS_URLS:
        try:
            events.extend(_fetch_rss(url, limit))
        except Exception:
            continue  # one dead feed must not kill the agent
        if len(events) >= limit:
            break
    return events[:limit]


# ---------------------------------------------------------------------------
# 3. Offline samples (always available)
# ---------------------------------------------------------------------------
def load_sample_events() -> list[NewsEvent]:
    raw = json.loads(config.SAMPLES_FILE.read_text(encoding="utf-8"))
    return [NewsEvent(**e) for e in raw]


def fetch_latest_news(limit: int = 5) -> tuple[list[NewsEvent], str]:
    """Priority: bitget-signal skill -> RSS -> samples. Returns (events, origin)."""
    try:
        events = fetch_bitget_signal_news(limit)
        if events:
            return events, "bitget-signal skill"
    except Exception as exc:
        skill_note = str(exc)
    else:
        skill_note = ""
    rss = fetch_rss_news(limit)
    if rss:
        origin = "RSS fallback"
        if skill_note:
            origin += f" (skill unavailable: {skill_note})"
        return rss, origin
    return load_sample_events()[:limit], "bundled samples (offline demo mode)"
