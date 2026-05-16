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
BENCHMARK = "SPY"           # used for index.html / performance1.html comparisons
START_DATE = "2023-05-10"   # 2 days before first allocation
END_DATE   = (date.today() + timedelta(days=1)).strftime("%Y-%m-%d")

START_VALUE  = 10000.0
TRADING_DAYS = 252

MARKER_START = "// ── PERFORMANCE_DATA_START"
MARKER_END   = "// ── PERFORMANCE_DATA_END ──"


# ── 1. download prices ───────────────────────────────────────────────────
all_symbols = TICKERS + [BENCHMARK]
print(f"Downloading {len(all_symbols)} symbols from {START_DATE} to {END_DATE}...")
raw = yf.download(all_symbols, start=START_DATE, end=END_DATE,
                  auto_adjust=True, progress=False, group_by="ticker")

if raw.empty:
    print("\nERROR: yfinance returned no data. Check your internet connection.")
    sys.exit(1)

# Flatten multi-level columns into {ticker: {date_iso: close}}
prices = {}
for t in all_symbols:
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


# ── 5. SPY benchmark over the same windows ──────────────────────────────
spy_prices = prices.get(BENCHMARK, {})
if not spy_prices:
    print(f"\nWARN: no {BENCHMARK} data; benchmark stats will be skipped.")
    spy_stats_1yr = spy_stats_3yr = None
else:
    # Build SPY equity curve matching our trading-day window
    spy_dates = sorted(spy_prices.keys())
    # Align to first equity date we have
    try:
        first_idx = next(i for i, d in enumerate(spy_dates) if d >= equity_dates[0])
        last_idx  = max(i for i, d in enumerate(spy_dates) if d <= equity_dates[-1])
    except (ValueError, StopIteration):
        first_idx, last_idx = 0, len(spy_dates) - 1
    spy_window  = spy_dates[first_idx:last_idx + 1]
    spy_p0 = spy_prices[spy_window[0]]
    spy_eq_dates  = list(spy_window)
    spy_eq_values = [START_VALUE * (spy_prices[d] / spy_p0) for d in spy_window]
    spy_stats_3yr = compute_stats(spy_eq_dates, spy_eq_values)
    if len(spy_eq_values) >= 253:
        spy_stats_1yr = compute_stats(spy_eq_dates[-253:], spy_eq_values[-253:])
    else:
        spy_stats_1yr = spy_stats_3yr
    print(f"\nSPY 3-yr: {spy_stats_3yr['cum_return']:+.2f}% cum, "
          f"{spy_stats_3yr['ann_return']:+.2f}% ann, max DD {spy_stats_3yr['max_drawdown']:.2f}%")


# ── 6. inject into Algorithm185History.html ──────────────────────────────
# Sample the equity curves down to ~30 evenly-spaced points so the chart
# stays readable. Both BLEE and SPY are aligned on the same date axis.
def _sample(dates, values, n=30):
    if len(values) <= n:
        return list(dates), [round(v, 2) for v in values]
    step = (len(values) - 1) / (n - 1)
    out_d, out_v = [], []
    for i in range(n):
        idx = min(int(round(i * step)), len(values) - 1)
        out_d.append(dates[idx])
        out_v.append(round(values[idx], 2))
    return out_d, out_v

curve_dates, curve_blee = _sample(equity_dates, equity_values, n=30)
# Re-sample SPY curve on the same date indices when available
if spy_prices:
    spy_eq_dict = dict(zip(spy_eq_dates, spy_eq_values))
    # For each sample date, find the closest SPY date <= it
    spy_dates_sorted = sorted(spy_eq_dict.keys())
    curve_spy = []
    j = 0
    for d in curve_dates:
        while j + 1 < len(spy_dates_sorted) and spy_dates_sorted[j + 1] <= d:
            j += 1
        curve_spy.append(round(spy_eq_dict[spy_dates_sorted[j]], 2))
else:
    curve_spy = None

payload = {
    "updated":      datetime.now().strftime("%Y-%m-%d %H:%M"),
    "stats_1yr":    stats_1yr,
    "stats_3yr":    stats_3yr,
    "spy_1yr":      spy_stats_1yr,
    "spy_3yr":      spy_stats_3yr,
    "equity_curve": {
        "labels": curve_dates,
        "blee":   curve_blee,
        "spy":    curve_spy,
    },
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

# Also write a standalone JSON file so the chart can fetch() it without
# embedding the equity curve into the HTML (keeps Algorithm185History.html
# from getting bloated with sample data).
JSON_FILE = SCRIPT_DIR / "performance_data.json"
JSON_FILE.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
print(f"Wrote standalone {JSON_FILE.name} ({JSON_FILE.stat().st_size} bytes)")


# ── 7. patch index.html + performance1.html via data-perf attributes ─────
def fmt_pct(n, no_decimal=False, plus_for_positive=True):
    if n is None:
        return "—"
    s = f"{n:.0f}%" if no_decimal else f"{n:.2f}%"
    if plus_for_positive and n > 0 and not s.startswith("+"):
        s = "+" + s
    # Use the proper minus sign (−) for negative values to match style on the pages
    if s.startswith("-"):
        s = "−" + s[1:]
    return s

def fmt_pp(n):
    """percentage-points delta, with + sign"""
    if n is None: return "—"
    return ("+" if n >= 0 else "−") + f"{abs(n):.1f}pp"

def fmt_dollar(n):
    if n is None: return "—"
    return f"${round(n):,}"

# Build the replacement map keyed by data-perf id
edge_cum = (stats_3yr['cum_return'] - (spy_stats_3yr['cum_return'] if spy_stats_3yr else 0))
edge_ann = (stats_3yr['ann_return'] - (spy_stats_3yr['ann_return'] if spy_stats_3yr else 0))
edge_dd_ratio = abs(spy_stats_3yr['max_drawdown'] / stats_3yr['max_drawdown']) if (spy_stats_3yr and stats_3yr['max_drawdown'] != 0) else 0
edge_final = stats_3yr['end_value'] - (spy_stats_3yr['end_value'] if spy_stats_3yr else 0)

perf_replacements = {
    "blee_cum_3yr":   fmt_pct(stats_3yr['cum_return']),
    "blee_ann_3yr":   fmt_pct(stats_3yr['ann_return']),
    "blee_dd_3yr":    fmt_pct(stats_3yr['max_drawdown']),
    "blee_final_3yr": fmt_dollar(stats_3yr['end_value']),
}
if spy_stats_3yr:
    perf_replacements.update({
        "spy_cum_3yr":   fmt_pct(spy_stats_3yr['cum_return']),
        "spy_ann_3yr":   fmt_pct(spy_stats_3yr['ann_return']),
        "spy_dd_3yr":    fmt_pct(spy_stats_3yr['max_drawdown']),
        "spy_final_3yr": fmt_dollar(spy_stats_3yr['end_value']),
        "edge_cum_3yr":  fmt_pp(edge_cum) + " ahead",
        "edge_ann_3yr":  fmt_pp(edge_ann),
        "edge_dd_3yr":   f"{edge_dd_ratio:.1f}× safer" if edge_dd_ratio else "—",
        "edge_final_3yr": ("+" if edge_final >= 0 else "−") + fmt_dollar(abs(edge_final)).lstrip("$").join(["$", ""]),
    })

def patch_file(path: Path, replacements: dict):
    if not path.exists():
        print(f"  SKIP: {path.name} not found")
        return
    text = path.read_text(encoding="utf-8")
    n = 0
    for key, val in replacements.items():
        # Match data-perf="key" OR data-perf-label="key"
        for attr in ("data-perf", "data-perf-label"):
            pat = re.compile(
                r'(<[^>]+' + attr + r'="' + re.escape(key) + r'"[^>]*>)([^<]*)(</[^>]+>)'
            )
            new_text, count = pat.subn(lambda m: m.group(1) + val + m.group(3), text)
            if count:
                text = new_text
                n += count
    path.write_text(text, encoding="utf-8")
    print(f"  {path.name}: patched {n} cells")


# Build period-header labels using actual start/end dates from the equity curve
def iso_to_mdy(iso):
    if not iso or "-" not in iso:
        return iso or ""
    y, m, d = iso.split("-")
    return f"{int(m):02d}/{int(d):02d}/{int(y)}"

period_3yr_label = (
    "\U0001F4C5 Performance on 3 year period from "
    + iso_to_mdy(stats_3yr["start_date"]) + " to " + iso_to_mdy(stats_3yr["end_date"])
)
period_6yr_label = (
    "\U0001F4C5 Performance on full "
    + str(round(stats_3yr["n_days"] / 252)) + "-year period from "
    + iso_to_mdy(stats_3yr["start_date"]) + " to " + iso_to_mdy(stats_3yr["end_date"])
    + " (Full Backtest)"
)

perf_replacements["period_3yr"] = period_3yr_label
perf_replacements["period_6yr"] = period_6yr_label

print()
print("Patching index.html + performance1.html...")
for fp in [SCRIPT_DIR / "index.html", SCRIPT_DIR / "performance1.html"]:
    patch_file(fp, perf_replacements)
