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
import re
import sys
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
    print(line)
    with open(LOG_PATH, "a") as f:
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
    return data.get("today_allocations", []), data.get("total_value", 0)


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
    """Returns (label, hex_color, arrow)."""
    if score > 20:   return ("Strong Uptrend",            "#16a34a", "↑↑")
    if score > 10:   return ("Positive (Uptrend)",         "#22c55e", "↑")
    if score > 0:    return ("Leaning Positive",           "#86efac", "↗")
    if score == 0:   return ("Neutral — Hold Gold/SGOV",   "#f59e0b", "→")
    if score > -10:  return ("Leaning Negative",           "#fca5a5", "↘")
    if score > -20:  return ("Negative (Downtrend)",       "#ef4444", "↓")
    return                  ("Clear Downtrend",            "#dc2626", "↓↓")


def allocation_groups(breakdown: list[dict]) -> tuple[float, float, float]:
    """Returns (positive_weight_pct, negative_weight_pct, neutral_weight_pct)."""
    pos = sum(b["weight"] for b in breakdown if b["point"] > 0)
    neg = sum(b["weight"] for b in breakdown if b["point"] < 0)
    neu = sum(b["weight"] for b in breakdown if b["point"] == 0)
    return round(pos, 2), round(neg, 2), round(neu, 2)


# ── Fetch news from Yahoo Finance RSS ────────────────────────────────────────

NEWS_FEEDS = [
    "https://finance.yahoo.com/news/rssindex",           # Yahoo Finance general
    "https://feeds.content.dowjones.io/public/rss/mw_marketpulse",  # MarketWatch
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
    """Fetch top market news from RSS feeds. Falls back to hardcoded items."""
    items: list[dict] = []
    for feed_url in NEWS_FEEDS:
        if len(items) >= max_items:
            break
        try:
            req = urllib.request.Request(
                feed_url,
                headers={"User-Agent": "Mozilla/5.0 (blee-market-report/1.0)"},
            )
            with urllib.request.urlopen(req, timeout=12) as resp:
                xml = resp.read().decode("utf-8", errors="ignore")

            # Minimal RSS parser (no external libs)
            entries = re.findall(r"<item>(.*?)</item>", xml, re.DOTALL)
            for entry in entries:
                if len(items) >= max_items:
                    break
                title_m = re.search(r"<title>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>", entry, re.DOTALL)
                link_m  = re.search(r"<link>(.*?)</link>", entry)
                desc_m  = re.search(r"<description>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</description>", entry, re.DOTALL)
                if not title_m:
                    continue
                title = re.sub(r"<[^>]+>", "", title_m.group(1)).strip()
                link  = link_m.group(1).strip() if link_m else ""
                desc  = re.sub(r"<[^>]+>", "", (desc_m.group(1) if desc_m else "")).strip()
                desc  = desc[:280] + ("…" if len(desc) > 280 else "")
                if not title:
                    continue
                tag, tag_cls = classify_tag(title)
                items.append({
                    "tag":       tag,
                    "tag_class": tag_cls,
                    "title":     title,
                    "body":      desc or title,
                    "source":    "Yahoo Finance",
                    "url":       link or "https://finance.yahoo.com/",
                })
        except Exception as exc:
            log(f"  (news fetch failed for {feed_url}: {exc})")

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

    allocs, total_value = load_allocations(ALLOC_HTML)
    log(f"Loaded {len(allocs)} ETF allocations from {ALLOC_HTML.name}")

    # Score
    score, breakdown = calculate_score(allocs, points)
    label, color, arrow = market_temperature(score)
    pos_w, neg_w, neu_w = allocation_groups(breakdown)

    log(f"Composite score: {score:+.2f} → {label}")

    # Dates
    now = dt.datetime.now()
    tomorrow = (now + dt.timedelta(days=1)).strftime("%B %d, %Y")
    today_str = now.strftime("%B %d, %Y")
    generated = now.strftime("%m/%d/%Y %I:%M %p")

    # News
    news = fetch_news(3)
    log(f"Fetched {len(news)} news items")

    # Build report dict
    report = {
        "generated":      generated,
        "report_date":    today_str,
        "for_date":       f"{tomorrow} (Tomorrow)",
        "score":          score,
        "temperature":    label,
        "temp_color":     color,
        "temp_arrow":     arrow,
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
