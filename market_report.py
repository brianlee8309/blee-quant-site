#!/usr/bin/env python3
"""
market_report.py — BLEE Daily Market Temperature Report Generator

Reads Index_50_point.csv and the latest Composer allocation (index_50.html),
calculates a weighted composite score, fetches the top 3 market news headlines
from Yahoo Finance RSS, then regenerates marketDailySummary.html.

Run automatically by run.bat after the allocation pull, or manually:
    python market_report.py
"""

from __future__ import annotations

import csv
import datetime as dt
import io
import json
import os
import re
import sys
import threading

# ── 3-minute hard cap ─────────────────────────────────────────────────────────
# If the script is still running after 2m55s (e.g. a hung network call),
# the watchdog thread forces a clean exit so run.bat is never stalled.
_TIMEOUT_SECONDS = 175   # 2m55s — leaves 5s margin before the 3-min window

def _watchdog() -> None:
    import time
    from pathlib import Path as _Path
    time.sleep(_TIMEOUT_SECONDS)
    _ts = dt.datetime.now().isoformat(timespec="seconds")
    msg = f"[{_ts}] market_report: WATCHDOG — exceeded {_TIMEOUT_SECONDS}s, forcing exit"
    print(msg)
    try:
        _log = _Path(__file__).resolve().parent / "composer_run.log"
        with open(_log, "a") as f:
            f.write(msg + "\n")
    except Exception:
        pass
    os._exit(1)

threading.Thread(target=_watchdog, daemon=True).start()
import urllib.request
from pathlib import Path

SCRIPT_DIR    = Path(__file__).resolve().parent
POINTS_CSV    = SCRIPT_DIR / "Index_50_point.csv"
ALLOC_HTML    = SCRIPT_DIR / "index_50.html"
TEMPLATE_HTML = SCRIPT_DIR / "marketDailySummary.html"
OUTPUT_HTML   = SCRIPT_DIR / "marketDailySummary.html"  # same file; we patch in-place
LOG_PATH      = SCRIPT_DIR / "composer_run.log"


def log(msg: str) -> None:
    ts = dt.datetime.now().isoformat(timespec="seconds")
    line = f"[{ts}] market_report: {msg}"
    # Windows cmd uses cp1252 by default — safely replace un-encodable chars
    try:
        print(line)
    except UnicodeEncodeError:
        enc = sys.stdout.encoding or "cp1252"
        print(line.encode(enc, errors="replace").decode(enc))
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(line + "\n")


# ── Load ETF points ───────────────────────────────────────────────────────────

def load_points(path: Path) -> dict[str, float]:
    raw = path.read_bytes().replace(b"\x00", b"").lstrip(b"\xef\xbb\xbf")
    points: dict[str, float] = {}
    for row in csv.DictReader(io.StringIO(raw.decode("utf-8"))):
        ticker = (row.get("Index") or "").strip()
        try:
            pt = float((row.get("Potint") or row.get("Point") or "0").strip())
        except ValueError:
            pt = 0.0
        if ticker:
            points[ticker] = pt
    return points


# ── Extract allocations from index_50.html ───────────────────────────────────

def load_allocations(path: Path) -> list[dict]:
    html = path.read_text(encoding="utf-8")
    idx = html.find("const DATA = ")
    if idx == -1:
        return []
    chunk = html[idx + len("const DATA = "):]
    depth = 0
    end = 0
    for i, ch in enumerate(chunk):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                break
    data = json.loads(chunk[:end])
    return data.get("today_allocations", []), data.get("total_value", 0), data.get("last_updated", "")


# ── Score calculation ─────────────────────────────────────────────────────────

def calculate_score(allocs: list[dict], points: dict[str, float]) -> tuple[float, list[dict]]:
    score = 0.0
    breakdown = []
    for a in allocs:
        t = a["ticker"]
        w = a["weight_pct"]
        p = points.get(t, 0.0)
        contrib = w * p
        score += contrib
        breakdown.append({
            "ticker":       t,
            "weight":       round(w, 4),
            "point":        p,
            "contribution": round(contrib, 4),
            "value":        round(a.get("market_value", 0), 2),
        })
    return round(score, 4), breakdown


def market_temperature(score: float) -> tuple[str, str, str]:
    """Returns (label, hex_color, arrow).
    Positive tiers (0–30 / 30–50 / 50+) use clear-sky language.
    Negative tiers (0 to -50 = rain, below -50 = thunderstorm).
    """
    if score > 50:   return ("Nice Blue Sky Ahead",        "#16a34a", "^")
    if score > 30:   return ("Almost Clear Sky All Day",   "#22c55e", "^")
    if score > 0:    return ("Partly Clear Sky Likely",    "#86efac", "^")
    if score == 0:   return ("Neutral — Hold Gold/SGOV",   "#f59e0b", "-")
    if score > -50:  return ("Rain in the Forecast",       "#ef4444", "v")
    return                  ("Thunderstorm Warning",       "#dc2626", "v")


def allocation_groups(breakdown: list[dict]) -> tuple[float, float, float]:
    """Returns (positive_weight_pct, negative_weight_pct, neutral_weight_pct)."""
    pos = sum(b["weight"] for b in breakdown if b["point"] > 0)
    neg = sum(b["weight"] for b in breakdown if b["point"] < 0)
    neu = sum(b["weight"] for b in breakdown if b["point"] == 0)
    return round(pos, 2), round(neg, 2), round(neu, 2)


# ── Fetch news from Yahoo Finance RSS ────────────────────────────────────────

# Public RSS feeds — no login required for headlines/summaries.
# WSJ and Barron's paywall applies to full articles, not RSS titles+snippets.
NEWS_FEEDS = [
    ("https://feeds.a.dj.com/rss/RSSMarketsMain.xml",                                              "WSJ"),
    ("https://www.barrons.com/xml/rss/3_7019.xml",                                                 "Barron's"),
    ("https://news.google.com/rss/search?q=stock+market+today&hl=en-US&gl=US&ceid=US:en",          "Google News"),
    ("https://www.bing.com/news/search?q=US+stock+market+today&format=rss",                        "Bing News"),
    ("https://finance.yahoo.com/news/rssindex",                                                     "Yahoo Finance"),
    ("https://feeds.content.dowjones.io/public/rss/mw_marketpulse",                                "MarketWatch"),
]

FALLBACK_NEWS = [
    {
        "tag": "MACRO",
        "tag_class": "tag-macro",
        "title": "April CPI Release — The Week's Make-or-Break Catalyst",
        "body": "The April Consumer Price Index lands Tuesday at 8:30 AM ET, with consensus calling for headline inflation of 3.7% year-over-year and core at 2.7% YoY. A hotter-than-expected print would compress Fed rate-cut expectations and could reverse the S&P 500's six-week winning streak.",
        "source": "CNBC / Gotrade",
        "url": "https://www.heygotrade.com/en/news/weekly-economic-outlook-2026-05-11/",
    },
    {
        "tag": "FED POLICY",
        "tag_class": "tag-fed",
        "title": "Fed Chair Transition: Powell Out, Warsh Confirmed This Week",
        "body": "Jerome Powell's term as Federal Reserve Chair ends Friday May 15. The US Senate is expected to confirm Kevin Warsh as his successor — viewed as more open to rate cuts, yet still conditional on significantly softer inflation data.",
        "source": "CNBC",
        "url": "https://www.cnbc.com/2026/04/29/fed-powell-warsh-interest-rates.html",
    },
    {
        "tag": "GEOPOLITICAL RISK",
        "tag_class": "tag-risk",
        "title": "US-Iran Tensions Elevate Energy Prices; Trump-Xi Summit Watches AI Guardrails",
        "body": "Ongoing US-Iran tensions have pushed energy prices higher and disrupted global trade routes. A Trump-Xi summit on May 14–15 on AI governance could move semiconductor names sharply. Goldman Sachs: 'equity market gyrations will likely continue to mirror geopolitical volatility.'",
        "source": "Goldman Sachs / Gotrade",
        "url": "https://www.heygotrade.com/en/news/weekly-economic-outlook-2026-05-11/",
    },
]

TAG_MAP = {
    "fed":         ("FED POLICY",       "tag-fed"),
    "inflation":   ("MACRO",            "tag-macro"),
    "cpi":         ("MACRO",            "tag-macro"),
    "gdp":         ("MACRO",            "tag-macro"),
    "recession":   ("MACRO",            "tag-macro"),
    "market":      ("EQUITY",           "tag-equity"),
    "s&p":         ("EQUITY",           "tag-equity"),
    "stock":       ("EQUITY",           "tag-equity"),
    "nasdaq":      ("EQUITY",           "tag-equity"),
    "geopolit":    ("GEOPOLITICAL RISK","tag-risk"),
    "iran":        ("GEOPOLITICAL RISK","tag-risk"),
    "china":       ("GEOPOLITICAL RISK","tag-risk"),
    "trade":       ("GEOPOLITICAL RISK","tag-risk"),
}


def classify_tag(title: str) -> tuple[str, str]:
    low = title.lower()
    for kw, (tag, cls) in TAG_MAP.items():
        if kw in low:
            return tag, cls
    return ("MARKET NEWS", "tag-equity")


def fetch_news(max_items: int = 3) -> list[dict]:
    """Fetch top market news from multiple RSS feeds. Falls back to hardcoded items.
    Tries WSJ, Barron's, Google News, Bing News, Yahoo Finance, MarketWatch in order.
    All feeds are public RSS — no login required for headlines and snippets.
    """
    items: list[dict] = []
    seen_titles: set[str] = set()

    for feed_url, source_name in NEWS_FEEDS:
        if len(items) >= max_items:
            break
        try:
            req = urllib.request.Request(
                feed_url,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    "Accept": "application/rss+xml, application/xml, text/xml, */*",
                },
            )
            with urllib.request.urlopen(req, timeout=18) as resp:
                xml = resp.read().decode("utf-8", errors="ignore")

            entries = re.findall(r"<item>(.*?)</item>", xml, re.DOTALL)
            for entry in entries:
                if len(items) >= max_items:
                    break
                title_m = re.search(r"<title>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>", entry, re.DOTALL)
                link_m  = re.search(r"<link[^>]*>(.*?)</link>", entry)
                desc_m  = re.search(r"<description>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</description>", entry, re.DOTALL)
                if not title_m:
                    continue
                title = re.sub(r"<[^>]+>", "", title_m.group(1)).strip()
                link  = link_m.group(1).strip() if link_m else ""
                desc  = re.sub(r"<[^>]+>", "", (desc_m.group(1) if desc_m else "")).strip()
                desc  = desc[:300] + ("…" if len(desc) > 300 else "")
                if not title or title in seen_titles:
                    continue
                seen_titles.add(title)
                tag, tag_cls = classify_tag(title)
                items.append({
                    "tag":       tag,
                    "tag_class": tag_cls,
                    "title":     title,
                    "body":      desc or title,
                    "source":    source_name,
                    "url":       link or "https://finance.yahoo.com/",
                })
            log(f"  News: got {len(items)} item(s) so far after {source_name}")
        except Exception as exc:
            log(f"  News fetch failed ({source_name}): {exc}")

    if len(items) < max_items:
        # Pad with fallback items not already present
        existing_titles = {i["title"] for i in items}
        for fb in FALLBACK_NEWS:
            if len(items) >= max_items:
                break
            if fb["title"] not in existing_titles:
                items.append(fb)

    return items[:max_items]


# ── Patch HTML with new REPORT JSON ──────────────────────────────────────────

def patch_html(report: dict) -> None:
    html = OUTPUT_HTML.read_text(encoding="utf-8")
    new_json = json.dumps(report, ensure_ascii=False)
    patched = re.sub(
        r"const REPORT = /\* __REPORT_JSON__ \*/ \{.*?\};",
        f"const REPORT = /* __REPORT_JSON__ */ {new_json};",
        html,
        flags=re.DOTALL,
    )
    if patched == html:
        # Fallback: replace the entire const REPORT = ... ; block
        patched = re.sub(
            r"const REPORT = /\* __REPORT_JSON__ \*/ .*?;",
            f"const REPORT = /* __REPORT_JSON__ */ {new_json};",
            html,
        )
    OUTPUT_HTML.write_text(patched, encoding="utf-8")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> int:
    log("=== Market report generation started ===")

    if not POINTS_CSV.exists():
        log(f"ERROR: Points CSV not found at {POINTS_CSV}")
        return 1
    if not ALLOC_HTML.exists():
        log(f"ERROR: Allocation HTML not found at {ALLOC_HTML}")
        return 1

    # Load data
    points = load_points(POINTS_CSV)
    log(f"Loaded {len(points)} ETF points from {POINTS_CSV.name}")

    allocs, total_value, last_updated = load_allocations(ALLOC_HTML)
    log(f"Loaded {len(allocs)} ETF allocations from {ALLOC_HTML.name}")

    # Score
    score, breakdown = calculate_score(allocs, points)
    label, color, arrow = market_temperature(score)
    pos_w, neg_w, neu_w = allocation_groups(breakdown)

    log(f"Composite score: {score:+.2f} -> {label}")

    # Dates — for_date = next business day after the allocation date
    now = dt.datetime.now()
    generated = now.strftime("%m/%d/%Y %I:%M %p")
    today_str = now.strftime("%B %d, %Y")

    def next_business_day(date_str: str) -> dt.date:
        """Return the next weekday (Mon–Fri) after the given ISO date string."""
        try:
            base = dt.date.fromisoformat(date_str)
        except (ValueError, TypeError):
            base = dt.date.today()
        nxt = base + dt.timedelta(days=1)
        while nxt.weekday() >= 5:   # 5=Sat, 6=Sun
            nxt += dt.timedelta(days=1)
        return nxt

    for_date_obj = next_business_day(last_updated or dt.date.today().isoformat())
    for_date_str = for_date_obj.strftime("%B %d, %Y")

    # News
    news = fetch_news(3)
    log(f"Fetched {len(news)} news items")

    # Build report dict
    report = {
        "generated":      generated,
        "report_date":    today_str,
        "for_date":       for_date_str,
        "score":          score,
        "temperature":    label,
        "temp_color":     color,
        "temp_arrow":     arrow,
        "weather_label":  {
            "Thunderstorm Warning":      "⛈️ Thunderstorm Warning",
            "Rain in the Forecast":      "🌧️ Rain in the Forecast",
            "Neutral — Hold Gold/SGOV":  "⛅ Overcast — Neutral",
            "Partly Clear Sky Likely":   "🌤️ Partly Clear Sky",
            "Almost Clear Sky All Day":  "☀️ Almost Clear Sky All Day",
            "Nice Blue Sky Ahead":       "🌈 Nice Blue Sky Ahead",
        }.get(label, label),
        "positive_weight": pos_w,
        "negative_weight": neg_w,
        "neutral_weight":  neu_w,
        "total_value":     round(total_value, 2),
        "breakdown":       breakdown,
        "news":            news,
    }

    patch_html(report)
    log(f"Updated {OUTPUT_HTML.name} with score={score:+.2f} ({label})")
    log("=== Market report generation complete ===")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        log(f"FATAL: {type(e).__name__}: {e}")
        sys.exit(1)
