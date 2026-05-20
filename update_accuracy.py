"""
update_accuracy.py
──────────────────
Downloads daily closing prices for QQQ, SPY, and DIA via yfinance,
then injects the data directly into Algorithm185History.html so the
Signal Accuracy column shows ✅/❌ for every directional trading day.

Run manually or schedule via Windows Task Scheduler (after market close, e.g. 5:00 PM ET).
"""

import json
import re
import sys
from datetime import datetime, date, timedelta
from pathlib import Path

# ── Try importing yfinance ───────────────────────────────────────────────
try:
    import yfinance as yf
except ImportError:
    print("yfinance not found. Installing...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "yfinance", "--quiet"])
    import yfinance as yf

# ── Config ───────────────────────────────────────────────────────────────
HTML_FILE   = Path(__file__).parent / "Algorithm185History.html"
SYMBOLS     = ["QQQ", "SPY", "DIA"]
START_DATE  = "2023-05-10"   # a few days before the first allocation entry
END_DATE    = (date.today() + timedelta(days=1)).strftime("%Y-%m-%d")  # tomorrow to include today

MARKER_START = "// ── PRICE_DATA_START"
MARKER_END   = "// ── PRICE_DATA_END ──"

# ── Download price data ───────────────────────────────────────────────────
print(f"Downloading {', '.join(SYMBOLS)} from {START_DATE} to {END_DATE}...")
price_map = {}   # { "QQQ": { "2023-05-12": {"close": "330.45", "prev": "328.12", "change": "up"} } }

for sym in SYMBOLS:
    print(f"  Fetching {sym}...", end=" ")
    try:
        df = yf.download(sym, start=START_DATE, end=END_DATE,
                         auto_adjust=True, progress=False)
        if df.empty:
            print("no data returned — skipping")
            continue

        # Flatten multi-level columns if present
        if hasattr(df.columns, "levels"):
            df.columns = df.columns.get_level_values(0)

        closes = df["Close"].dropna()
        days_map = {}
        dates = list(closes.index)
        for i in range(1, len(dates)):
            dt_str   = dates[i].strftime("%Y-%m-%d")
            curr     = float(closes.iloc[i])
            prev     = float(closes.iloc[i - 1])
            if curr > prev * 1.0005:
                change = "up"
            elif curr < prev * 0.9995:
                change = "down"
            else:
                change = "flat"
            days_map[dt_str] = {
                "close":  f"{curr:.2f}",
                "prev":   f"{prev:.2f}",
                "change": change
            }

        price_map[sym] = days_map
        up   = sum(1 for v in days_map.values() if v["change"] == "up")
        down = sum(1 for v in days_map.values() if v["change"] == "down")
        print(f"{len(days_map)} days  (▲{up} up / ▼{down} down)")

    except Exception as e:
        print(f"ERROR: {e}")

if not price_map:
    print("\n❌ No data downloaded. Check your internet connection.")
    sys.exit(1)

# ── Build replacement JS block ────────────────────────────────────────────
now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
price_json = json.dumps(price_map, separators=(",", ":"))

new_block = (
    f"// ── PRICE_DATA_START (auto-updated by update_accuracy.py — do not edit manually) ──\n"
    f"const PRICE_DATA = {price_json};\n"
    f'const PRICE_DATA_UPDATED = "{now_str}";\n'
    f"// ── PRICE_DATA_END ──"
)

# ── Read and replace HTML ─────────────────────────────────────────────────
html_text = HTML_FILE.read_text(encoding="utf-8")

pattern = re.compile(
    re.escape(MARKER_START) + r".*?" + re.escape(MARKER_END),
    re.DOTALL
)

if not pattern.search(html_text):
    print(f"\n❌ Could not find injection markers in {HTML_FILE.name}")
    print(f"   Expected to find: {MARKER_START}")
    sys.exit(1)

new_html = pattern.sub(new_block, html_text)
HTML_FILE.write_text(new_html, encoding="utf-8")

# ── Integrity check — catch silent truncation immediately after write ──────
import importlib.util as _ilu, pathlib as _pl
_vspec = _ilu.spec_from_file_location("verify_html", _pl.Path(__file__).parent / "verify_html.py")
if _vspec:
    _vm = _ilu.module_from_spec(_vspec); _vspec.loader.exec_module(_vm)
    if not _vm.verify(HTML_FILE):
        print("\n❌ Aborting: integrity check failed after write. Restore with:")
        print(f"   git checkout HEAD -- {HTML_FILE.name}")
        sys.exit(1)

# ── Report accuracy stats ─────────────────────────────────────────────────
total_days = sum(len(v) for v in price_map.values())
print(f"\n✅ Injected {total_days} tota