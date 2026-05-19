"""
backfill_rsi.py — One-time script to backfill missing RSI-14 history and fix
                  the close=0 bug in rsi_history.csv.

Run once from Windows:
    cd C:\Kei\ComposerInvest
    python backfill_rsi.py

What it does:
  1. Re-fetches SPY data for all dates already in rsi_history.csv to fix close=0
  2. Fills in any missing trading days going back to the first entry
  3. Re-saves rsi_history.csv with correct data
  4. Injects the RSI history into Algorithm185History.html (RSI_INLINE_DATA_START block)
"""

import csv, datetime as dt, json, re, sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
RSI_CSV    = SCRIPT_DIR / "rsi_history.csv"
HTML_FILE  = SCRIPT_DIR / "Algorithm185History.html"
TICKER     = "SPY"
RSI_PERIOD = 14

# ── 1. Fetch full history via yfinance ────────────────────────────────────────
print("Fetching SPY data via yfinance...")
try:
    import yfinance as yf
except ImportError:
    sys.exit("ERROR: run  pip install yfinance --break-system-packages  first")

today = dt.date.today()
start = (today - dt.timedelta(days=120)).isoformat()   # 120 days = enough for RSI-14
df = yf.download(TICKER, start=start, end=(today + dt.timedelta(days=1)).isoformat(),
                 progress=False, auto_adjust=True)

if df is None or df.empty:
    sys.exit("ERROR: yfinance returned no data. Check internet connection.")

# Flatten multi-level columns if present
close_col = df["Close"]
if hasattr(close_col, "columns"):
    close_col = close_col.iloc[:, 0]

closes = close_col.dropna().tolist()
dates  = [d.date().isoformat() for d in df.index]
print(f"  Fetched {len(closes)} trading days  ({dates[0]} → {dates[-1]})")

# ── 2. Calculate RSI-14 (Wilder's method) ─────────────────────────────────────
def calc_rsi14(closes):
    if len(closes) < RSI_PERIOD + 1:
        return [None] * len(closes)
    gains = [max(closes[i]-closes[i-1], 0) for i in range(1, len(closes))]
    losses= [max(closes[i-1]-closes[i], 0) for i in range(1, len(closes))]
    avg_g = sum(gains[:RSI_PERIOD]) / RSI_PERIOD
    avg_l = sum(losses[:RSI_PERIOD]) / RSI_PERIOD
    rsi = [None] * RSI_PERIOD
    for i in range(RSI_PERIOD, len(gains)):
        avg_g = (avg_g * (RSI_PERIOD-1) + gains[i]) / RSI_PERIOD
        avg_l = (avg_l * (RSI_PERIOD-1) + losses[i]) / RSI_PERIOD
        rsi.append(100.0 if avg_l == 0 else round(100 - 100/(1+avg_g/avg_l), 2))
    return [None] + rsi  # align with closes

rsi_series = calc_rsi14(closes)

# ── 3. Build complete rows dict ───────────────────────────────────────────────
new_rows = {}
for i, (d, c, r) in enumerate(zip(dates, closes, rsi_series)):
    if r is not None:
        new_rows[d] = {"date": d, "ticker": TICKER,
                       "rsi14": round(r, 2), "close": round(c, 4)}

# ── 4. Load existing CSV and merge (keep any rows outside our fetch window) ───
existing = {}
if RSI_CSV.exists():
    with open(RSI_CSV, newline="") as f:
        for row in csv.DictReader(f):
            existing[row["date"]] = row

# Overlay new_rows (has correct closes) onto existing
merged = {**existing, **new_rows}
sorted_rows = sorted(merged.values(), key=lambda r: r["date"])

# Save CSV
with open(RSI_CSV, "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=["date","ticker","rsi14","close"])
    w.writeheader()
    w.writerows(sorted_rows)

print(f"\n✅ rsi_history.csv updated — {len(sorted_rows)} rows total")
for row in sorted_rows[-10:]:
    print(f"   {row['date']}  RSI={row['rsi14']:>6}  SPY=${float(row['close']):.2f}")

# ── 5. Inject RSI_INLINE_DATA into Algorithm185History.html ──────────────────
print(f"\nInjecting RSI data into {HTML_FILE.name}...")

if not HTML_FILE.exists():
    print("  WARNING: HTML file not found — skipping injection")
    sys.exit(0)

# Build newest-first list of last 30 trading days for inline embed
recent = sorted(sorted_rows, key=lambda r: r["date"], reverse=True)[:30]
js_array = "var RSI_INLINE_DATA = [\n"
for row in recent:
    js_array += f'  {{date:"{row["date"]}", rsi14:{row["rsi14"]}, close:{float(row["close"]):.4f}}},\n'
js_array += "];"

html = HTML_FILE.read_text(encoding="utf-8")
pattern = r'(// RSI_INLINE_DATA_START\n).*?(// RSI_INLINE_DATA_END)'
replacement = r'\g<1>' + js_array + '\n// RSI_INLINE_DATA_END'
new_html = re.sub(pattern, replacement, html, flags=re.DOTALL)

if new_html == html:
    print("  WARNING: RSI_INLINE_DATA markers not found in HTML — data not injected")
else:
    HTML_FILE.write_text(new_html, encoding="utf-8")
    print(f"  ✅ Injected {len(recent)} rows into Algorithm185History.html")

print("\nDone! Run  git add . && git commit -m 'Backfill RSI history' && git push")
