#!/usr/bin/env python3
"""NightShift Agent live dashboard (stdlib only, no pip install)."""
from __future__ import annotations
import json
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))

import agent as agent_mod  # noqa: E402
import broker as broker_mod  # noqa: E402
import config  # noqa: E402
from llm import interpret_event  # noqa: E402
from news import NewsEvent, fetch_latest_news, load_sample_events  # noqa: E402

CAPITAL = config.DEFAULT_CAPITAL
LIVE = False
LOCK = threading.Lock()
ROOT = Path(__file__).resolve().parent

def _page():
    return (ROOT / "dash_top.html").read_text(encoding="utf-8") + (
        ROOT / "dash_js.html").read_text(encoding="utf-8")


def _broker():
    return broker_mod.PaperBroker(CAPITAL, live=LIVE)


def _status():
    b = _broker()
    with LOCK:
        pnl = b.day_pnl_pct()
        halted = b.is_halted()
        pos = []
        for p in b.positions_list():
            mk = b.get_market_price(p["ticker"])
            pos.append({"id": p["order_id"], "dir": p["direction"].upper(),
                        "tk": p["ticker"], "en": p["price"], "mk": mk,
                        "u": broker_mod.PaperBroker._position_pnl_usd(p, mk)})
        log = []
        try:
            files = sorted(config.LOG_DIR.glob("agent-*.jsonl"))
            if files:
                lines = files[-1].read_text(encoding="utf-8").strip().splitlines()[-8:]
                for ln in lines:
                    try:
                        r = json.loads(ln)
                        log.append(str(r.get("timestamp", "")) + " | " +
                                   str((r.get("event") or {}).get("title", ""))[:55] +
                                   " -> " + str(r.get("result", ""))[:75])
                    except ValueError:
                        pass
        except OSError:
            pass
    ev, evorg = "No runs yet - press 1.", "-"
    if log:
        try:
            files = sorted(config.LOG_DIR.glob("agent-*.jsonl"))
            r = json.loads(files[-1].read_text(encoding="utf-8").strip().splitlines()[-1])
            ev = r["event"]["title"]
            evorg = "via " + str(r["event"].get("news_origin", ""))
        except (OSError, ValueError, KeyError, IndexError):
            pass
    eng = "llm (key set)" if config.OPENAI_API_KEY else "rules-fallback (no key)"
    return {"eq": CAPITAL, "n": len(pos), "mx": config.MAX_OPEN_POSITIONS,
            "pnl": pnl, "halted": halted, "live": LIVE, "engine": eng,
            "pos": pos, "ev": ev, "evorg": evorg, "log": log[::-1]}

def _run(sample=None, event=None, news=False, live=False):
    global LIVE
    if live:
        LIVE = True
    if news:
        evs, org = fetch_latest_news(5)
        if not evs:
            return {"err": "No news available."}
        ev, org = evs[0], org + " - dashboard"
    elif sample is not None:
        ss = load_sample_events()
        if not 1 <= int(sample) <= len(ss):
            return {"err": "sample must be 1..%d" % len(ss)}
        ev, org = ss[int(sample) - 1], "bundled sample #%s - dashboard" % sample
    elif event:
        ev = NewsEvent(title=str(event)[:160], source="dashboard-input", body=str(event))
        org = "manual input - dashboard"
    else:
        return {"err": "Pass sample, event, or news:true."}
    with LOCK:
        sig = interpret_event(ev.text())
        rec = agent_mod.run_event(ev, CAPITAL, news_origin=org, live=LIVE)
    rk = rec.get("risk", {})
    return {"engine": sig.engine, "why": sig.reasoning, "cf": sig.confidence,
            "tr": sig.trade, "tk": sig.ticker, "dir": (sig.direction or "").upper(),
            "sz": sig.size_pct, "ck": bool(rk.get("checked")),
            "ap": bool(rk.get("approved")),
            "rs": list(rk.get("reasons", []) or ["clean"]),
            "fs": rk.get("capped_size_pct"), "sp": rk.get("stop_pct")}




class H(BaseHTTPRequestHandler):
    server_version = "NightShift/0.2"

    def _j(self, o, code=200):
        b = json.dumps(o).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):  # noqa: N802
        if urlparse(self.path).path in ("/", "/index.html"):
            b = _page().encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(b)))
            self.end_headers()
            self.wfile.write(b)
        elif urlparse(self.path).path == "/api/status":
            self._j(_status())
        else:
            self._j({"err": "not found"}, 404)

    def do_POST(self):  # noqa: N802
        try:
            ln = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            ln = 0
        try:
            p = json.loads(self.rfile.read(ln) or b"{}")
        except ValueError:
            p = {}
        path = urlparse(self.path).path
        if path == "/api/run":
            self._j(_run(sample=p.get("sample"), event=p.get("event"),
                         news=bool(p.get("news")), live=bool(p.get("live"))))
        elif path == "/api/sim":
            try:
                self._j(_broker().simulate_loss(float(p.get("pct", 3.0))))
            except ValueError as e:
                self._j({"err": str(e)}, 400)
        elif path == "/api/reset":
            _broker().reset_demo_state()
            self._j({"ok": True})
        else:
            self._j({"err": "not found"}, 404)

    def log_message(self, f, *a):
        print("[dashboard] " + f % a)


def main():
    import argparse
    global CAPITAL
    ap = argparse.ArgumentParser(description="NightShift live dashboard (stdlib only)")
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--capital", type=float, default=config.DEFAULT_CAPITAL)
    ap.add_argument("--open", action="store_true")
    a = ap.parse_args()
    CAPITAL = a.capital
    srv = ThreadingHTTPServer(("127.0.0.1", a.port), H)
    print("NightShift dashboard -> http://localhost:%d (Ctrl+C, paper only)" % a.port)
    if a.open:
        threading.Timer(0.6, lambda: webbrowser.open("http://localhost:%d" % a.port)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
