"""
update_performance.py
─────────────────────
Computes BLEE-185 strategy performance from the daily allocation CSV and
historical Yahoo Finance prices, then injects the 1-year + 3-year stats
(annualized return, cumulative return, max drawdown) into Algorithm185History.html
between PERFORMANCE_DATA_START / PERFORMANCE_DATA_END markers.

Run manually or via run_signal.bat once per trading day after market close.

How the simulation works
------------------------
  1. Load 754 daily allocation rows from composer_allocations_185_3yr2.csv
  2. Download daily adjusted closes for each strategy ETF via yfinance
     (auto_adjust=True so SGOV/GLDM/GLD dividends are reinvested)
  3. For each day d with allocation A:
        daily_return = sum( A[ticker] * (price[t+1]/price[t] - 1) )
        portfolio[t+1] = portfolio[t] * (1 + daily_return)
  4. Compute 1-year (last 252 trading days) and 3-year (full history) stats:
        cum_return     = end/start - 1
        ann_return     = (end/start) ^ (252/n_days) - 1
        max_drawdown   = max( (peak - value) / peak ) across the period

  $USD allocation contributes 0% return (cash, no price change).
"""

import csv
import json
import re
import subprocess
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

# ── yfinance ──────────────────────────────────────────────────────────────
try:
    import yfinance as yf
except ImportError:
    print("yfinance not found. Installing...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "yfinance", "--quiet"])
    import yfinance as yf

# ── config ────────────────────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).parent
HTML_FILE = SCRIPT_DIR / "Algorithm185History.html"
CSV_FILE  = SCRIPT_DIR / "composer_allocations_185_3yr2.csv"

TICKERS = ["SGOV", "GLDM", "UPRO", "TQQQ", "TECL", "GLD", "UDOW", "SQQQ", "PSQ"]
START_DATE = "2023-05-10"   # 2 days before first allocation
END_DATE   = (date.today() + timedelta(days=1)).strftime("%Y-%m-%d")

START_VALUE  = 10000.0
TRADING_DAYS = 252

MARKER_START = "// ── PERFORMANCE_DATA_START"
MARKER_END   = "// ── PERFORMANCE_DATA_END ──"


# ── 1. download prices ───────────────────────────────────────────────────
print(f"Downloading {len(TICKERS)} ETFs from {START_DATE} to {END_DATE}...")
raw = yf.download(TICKERS, start=START_DATE, end=END_DATE,
                  auto_adjust=True, progress=False, group_by="ticker")

if raw.empty:
    print("\nERROR: yfinance returned no data. Check your internet connection.")
    sys.exit(1)

# Flatten multi-level columns into {ticker: {date_iso: close}}
prices = {}
for t in TICKERS:
    try:
        col = raw[t]["Close"] if (t, "Close") in raw.columns else raw["Close"][t]
    except (KeyError, AttributeError):
        try:
            col = raw["Close"]
        except KeyError:
            print(f"  WARN: no data for {t}, skipping")
            continue
    series = col.dropna()
    prices[t] = {d.strftime("%Y-%m-%d"): float(v) for d, v in series.items()}
    print(f"  {t}: {len(prices[t])} days")

if not prices:
    print("\nERROR: no price data parsed.")
    sys.exit(1)


# ── 2. load allocations ──────────────────────────────────────────────────
print(f"\nLoading allocations from {CSV_FILE.name}...")
with open(CSV_FILE, encoding="utf-8-sig") as f:
    rdr = csv.reader(f)
    header = next(rdr)     # Date,Day Traded,UPRO,GLDM,$USD,TECL,TQQQ,SGOV,GLD,UDOW,SQQQ,PSQ
    rows = list(rdr)

ticker_cols = header[2:]   # 10 ticker column names
allocations = []           # list of (iso_date, {ticker: weight_fraction})
for r in rows:
    raw_date = r[0].strip()
    if "/" in raw_date:
        m, d, y = raw_date.split("/")
        iso = f"{y}-{int(m):02d}-{int(d):02d}"
    else:
        iso = raw_date
    alloc = {}
    for col_idx, ticker in enumerate(ticker_cols):
        val = r[2 + col_idx].strip()
        if val and val != "-":
            pct = float(val.rstrip("%"))
            if pct > 0:
                alloc[ticker] = pct / 100.0
    allocations.append((iso, alloc))

# CSV is newest-first; we want oldest-first for forward simulation
allocations.sort(key=lambda x: x[0])
print(f"  Loaded {len(allocations)} allocation rows ({allocations[0][0]} -> {allocations[-1][0]})")


# ── 3. simulate portfolio value ──────────────────────────────────────────
# Get all trading days from yfinance (union across tickers)
all_trading_dates = sorted({d for sym in prices for d in prices[sym]})

# Build equity curve: portfolio[i] is the value AT END of day i
# Day i's allocation determines the return from day i to day i+1.
print(f"\nSimulating portfolio with ${START_VALUE:,.0f} starting value...")
equity_dates = []
equity_values = []

value = START_VALUE
prev_date = None
for d, alloc in allocations:
    # Find d and next trading day in price series
    if d not in all_trading_dates:
        # Skip allocation rows that don't have a matching trading day
        continue
    idx = all_trading_dates.index(d)
    if idx + 1 >= len(all_trading_dates):
        # No next trading day available (today is the last allocation)
        equity_dates.append(d)
        equity_values.append(value)
        break
    next_d = all_trading_dates[idx + 1]

    # Compute daily return = sum(weight * (price_next/price_today - 1))
    daily_return = 0.0
    for ticker, weight in alloc.items():
        if ticker == "$USD":
            continue       # cash, zero return
        p0 = prices.get(ticker, {}).get(d)
        p1 = prices.get(ticker, {}).get(next_d)
        if p0 and p1 and p0 > 0:
            daily_return += weight * (p1 / p0 - 1)

    # First entry: capture starting point
    if not equity_values:
        equity_dates.append(d)
        equity_values.append(value)
    value = value * (1 + daily_return)
    equity_dates.append(next_d)
    equity_values.append(value)

print(f"  Equity curve: {len(equity_values)} points, "
      f"${equity_values[0]:,.0f} -> ${equity_values[-1]:,.0f}")


# ── 4. compute stats ─────────────────────────────────────────────────────
def compute_stats(dates, values):
    if len(values) < 2:
        return None
    start_v, end_v = values[0], values[-1]
    n_days = len(values) - 1
    cum_return = (end_v / start_v - 1) * 100
    if n_days > 0 and start_v > 0:
        ann_return = ((end_v / start_v) ** (TRADING_DAYS / n_days) - 1) * 100
    else:
        ann_return = 0.0
    # max drawdown
    peak = values[0]
    max_dd = 0.0
    for v in values:
        if v > peak:
            peak = v
        if peak > 0:
            dd = (peak - v) / peak * 100
            if dd > max_dd:
                max_dd = dd
    return {
        "start_date":   dates[0],
        "end_date":     dates[-1],
        "start_value":  round(start_v, 2),
        "end_value":    round(end_v, 2),
        "cum_return":   round(cum_return, 2),
        "ann_return":   round(ann_return, 2),
        "max_drawdown": round(-max_dd, 2),   # negative number for "drawdown of -X%"
        "n_days":       n_days,
    }

stats_3yr = compute_stats(equity_dates, equity_values)
# 1-year window: take the last 253 points (252 trading days + start anchor)
if len(equity_values) >= 253:
    stats_1yr = compute_stats(equity_dates[-253:], equity_values[-253:])
else:
    stats_1yr = stats_3yr

print(f"\n3-year: {stats_3yr['cum_return']:+.2f}% cumulative, "
      f"{stats_3yr['ann_return']:+.2f}% annualized, max DD {stats_3yr['max_drawdown']:.2f}%")
print(f"1-year: {stats_1yr['cum_return']:+.2f}% cumulative, "
      f"{stats_1yr['ann_return']:+.2f}% annualized, max DD {stats_1yr['max_drawdown']:.2f}%")


# ── 5. inject into HTML ──────────────────────────────────────────────────
payload = {
    "updated":    datetime.now().strftime("%Y-%m-%d %H:%M"),
    "stats_1yr":  stats_1yr,
    "stats_3yr":  stats_3yr,
}
new_block = (
    f"{MARKER_START} (auto-updated by update_performance.py — do not edit manually) "
    "──\n"
    f"const PERFORMANCE_DATA = {json.dumps(payload, separators=(',', ':'))};\n"
    f"{MARKER_END}"
)

html_text = HTML_FILE.read_text(encoding="utf-8")
pattern = re.compile(
    re.escape(MARKER_START) + r".*?" + re.escape(MARKER_END),
    re.DOTALL,
)
if not pattern.search(html_text):
    print(f"\nERROR: markers not found in {HTML_FILE.name}")
    print(f"   Expected: {MARKER_START} ... {MARKER_END}")
    sys.exit(1)

new_html = pattern.sub(new_block, html_text)
HTML_FILE.write_text(new_html, encoding="utf-8")
print(f"\nInjected stats into {HTML_FILE.name} ({len(new_html):,} bytes)")
print(f"Updated: {payload['updated']}")
