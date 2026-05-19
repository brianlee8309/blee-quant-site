"""
rsi_tracker.py — SPY RSI-14 tracker for BLEE Quant Analytics
─────────────────────────────────────────────────────────────
• Fetches SPY daily closes via yfinance
• Calculates RSI-14 using Wilder's smoothed moving average (standard method)
• Appends today's value to rsi_history.csv (one row per trading day)
• Exposes helpers used by market_report.py:
      get_rsi_signal()  → (rsi_today, avg_10d, signal_label, score_adj)
      get_rsi_history() → list of last N rows as dicts

CSV format: date, ticker, rsi14, close
"""

import csv
import datetime as dt
import logging
import os
from pathlib import Path

log = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────
SCRIPT_DIR   = Path(__file__).parent
RSI_CSV      = SCRIPT_DIR / "rsi_history.csv"
TICKER       = "SPY"
RSI_PERIOD   = 14
HISTORY_DAYS = 60   # fetch 60 calendar days of price data to get stable RSI-14

# Signal thresholds and their score adjustments applied to the market composite
# Positive score → bullish/sunny; Negative → bearish/rain (matches market_report scale)
RSI_SIGNAL_TABLE = [
    # (min_avg_rsi, max_avg_rsi, label,                     score_adj)
    (75,  100, "Severely Overbought — strong bear lean",     -20),
    (65,   75, "Overbought — moderate bear lean",            -10),
    (55,   65, "Mildly Overbought — slight bear lean",        -5),
    (45,   55, "Neutral RSI",                                  0),
    (35,   45, "Mildly Oversold — slight bull lean",          +5),
    (25,   35, "Oversold — moderate bull lean",              +10),
    (  0,  25, "Severely Oversold — strong bull lean",       +20),
]

CSV_HEADER = ["date", "ticker", "rsi14", "close"]


# ── RSI calculation ───────────────────────────────────────────────────────────

def _calc_rsi14(closes: list[float]) -> list[float]:
    """Return RSI-14 series (same length as closes, NaN for first 14 values)."""
    if len(closes) < RSI_PERIOD + 1:
        return [float("nan")] * len(closes)

    gains, losses = [], []
    for i in range(1, len(closes)):
        delta = closes[i] - closes[i - 1]
        gains.append(max(delta, 0))
        losses.append(max(-delta, 0))

    # Seed with simple average of first 14 periods
    avg_gain = sum(gains[:RSI_PERIOD]) / RSI_PERIOD
    avg_loss = sum(losses[:RSI_PERIOD]) / RSI_PERIOD

    rsi_values = [float("nan")] * RSI_PERIOD  # pad for alignment with closes

    # Wilder smoothing
    for i in range(RSI_PERIOD, len(gains)):
        avg_gain = (avg_gain * (RSI_PERIOD - 1) + gains[i]) / RSI_PERIOD
        avg_loss = (avg_loss * (RSI_PERIOD - 1) + losses[i]) / RSI_PERIOD
        if avg_loss == 0:
            rsi_values.append(100.0)
        else:
            rs = avg_gain / avg_loss
            rsi_values.append(round(100 - (100 / (1 + rs)), 2))

    # Align: rsi_values has len = len(closes) - 1 entries after the pad
    return [float("nan")] + rsi_values  # index 0 has no RSI (no prior close)


# ── CSV helpers ───────────────────────────────────────────────────────────────

def _load_csv() -> list[dict]:
    """Load all rows from rsi_history.csv; return [] if file doesn't exist."""
    if not RSI_CSV.exists():
        return []
    with open(RSI_CSV, newline="") as f:
        return list(csv.DictReader(f))


def _save_csv(rows: list[dict]) -> None:
    with open(RSI_CSV, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CSV_HEADER)
        w.writeheader()
        w.writerows(rows)


def _last_n_business_days(rows: list[dict], n: int) -> list[dict]:
    """Return the n most-recent rows sorted oldest → newest."""
    dated = []
    for r in rows:
        try:
            dated.append((dt.date.fromisoformat(r["date"]), r))
        except (ValueError, KeyError):
            pass
    dated.sort(key=lambda x: x[0])
    return [r for _, r in dated[-n:]]


# ── Fetch & update ────────────────────────────────────────────────────────────

def fetch_and_store(today: dt.date | None = None) -> dict | None:
    """
    Fetch SPY closes, calculate RSI-14, append today's row to rsi_history.csv.
    Returns the new row dict, or None on failure.
    """
    today = today or dt.date.today()
    today_str = today.isoformat()

    # Skip if already stored for today
    existing = _load_csv()
    if any(r["date"] == today_str for r in existing):
        log.info(f"rsi_tracker: RSI-14 for {today_str} already stored, skipping fetch")
        return next(r for r in existing if r["date"] == today_str)

    try:
        import yfinance as yf
    except ImportError:
        log.error("rsi_tracker: yfinance not installed — run: pip install yfinance --break-system-packages")
        return None

    try:
        start = (today - dt.timedelta(days=HISTORY_DAYS)).isoformat()
        df = yf.download(TICKER, start=start, end=(today + dt.timedelta(days=1)).isoformat(),
                         progress=False, auto_adjust=True)
        if df is None or df.empty:
            log.warning(f"rsi_tracker: yfinance returned no data for {TICKER}")
            return None

        # yfinance with auto_adjust=True may return multi-level columns (ticker, field)
        # Flatten to a simple Series before calling .tolist()
        close_col = df["Close"]
        if hasattr(close_col, "columns"):          # multi-level: pick first ticker column
            close_col = close_col.iloc[:, 0]
        closes = close_col.dropna().tolist()
        dates  = [d.date().isoformat() for d in df.index]

        if len(closes) < RSI_PERIOD + 1:
            log.warning(f"rsi_tracker: not enough data to compute RSI-14 ({len(closes)} rows)")
            return None

        rsi_series = _calc_rsi14(closes)

        # Today's values (last element)
        rsi_today = rsi_series[-1]
        close_today = round(closes[-1], 4)
        price_date  = dates[-1]  # last market date (may be yesterday if market closed)

        if str(rsi_today) == "nan":
            log.warning("rsi_tracker: RSI-14 is NaN — not enough history")
            return None

        new_row = {
            "date":   price_date,
            "ticker": TICKER,
            "rsi14":  round(rsi_today, 2),
            "close":  close_today,
        }

        # Only append if this date isn't already in the CSV
        if not any(r["date"] == price_date for r in existing):
            existing.append(new_row)
            _save_csv(existing)
            log.info(f"rsi_tracker: stored RSI-14={rsi_today:.2f} for {price_date} (SPY close={close_today})")
        else:
            log.info(f"rsi_tracker: {price_date} already in CSV, skipping write")

        return new_row

    except Exception as e:
        log.error(f"rsi_tracker: fetch failed — {type(e).__name__}: {e}")
        return None


# ── Signal ────────────────────────────────────────────────────────────────────

def get_rsi_signal(lookback: int = 10) -> dict:
    """
    Read last `lookback` business days of RSI from CSV.
    Returns:
      {
        "rsi_today":   float,   # most recent RSI-14 value
        "avg_10d":     float,   # average over last N days
        "signal":      str,     # human-readable label
        "score_adj":   int,     # points to add to composite score (+/-)
        "history":     list[dict],  # last N rows
        "available":   bool,    # False if not enough data
      }
    """
    rows = _load_csv()
    history = _last_n_business_days(rows, lookback)

    if len(history) < 2:
        return {
            "rsi_today": None,
            "avg_10d":   None,
            "signal":    "RSI data unavailable",
            "score_adj": 0,
            "history":   history,
            "available": False,
        }

    try:
        rsi_values = [float(r["rsi14"]) for r in history]
    except (ValueError, KeyError):
        return {
            "rsi_today": None,
            "avg_10d":   None,
            "signal":    "RSI parse error",
            "score_adj": 0,
            "history":   history,
            "available": False,
        }

    rsi_today = rsi_values[-1]
    avg_10d   = round(sum(rsi_values) / len(rsi_values), 2)

    # Determine signal from average RSI over lookback window
    label, score_adj = "Neutral RSI", 0
    for lo, hi, lbl, adj in RSI_SIGNAL_TABLE:
        if lo <= avg_10d < hi:
            label, score_adj = lbl, adj
            break

    return {
        "rsi_today": round(rsi_today, 2),
        "avg_10d":   avg_10d,
        "signal":    label,
        "score_adj": score_adj,
        "history":   history,
        "available": True,
    }


def get_rsi_history(n: int = 10) -> list[dict]:
    """Return the last n RSI rows (oldest first)."""
    return _last_n_business_days(_load_csv(), n)


# ── RSI Override check ───────────────────────────────────────────────────────

def check_rsi_override(threshold: float = 76.0, lookback: int = 10) -> dict:
    """
    Returns whether the RSI override condition is active.

    Condition (both must be true):
      1. Today's RSI-14 > threshold (default 76)
      2. At least one of the previous `lookback` trading days also had RSI > threshold

    When active, callers should:
      - composer_pull_allocation: remap VIXY + SPXU allocations → TQQQ
      - market_report:            add +50 pts to composite score

    Returns:
      {
        "active":        bool,
        "rsi_today":     float | None,
        "over_threshold_days": list[dict],   # days in lookback window that exceeded threshold
        "threshold":     float,
        "reason":        str,
      }
    """
    rows = _load_csv()
    history = _last_n_business_days(rows, lookback + 1)  # +1 to include today + N prior

    if not history:
        return {"active": False, "rsi_today": None, "over_threshold_days": [],
                "threshold": threshold, "reason": "No RSI history available"}

    try:
        today_row   = history[-1]
        prior_rows  = history[:-1]   # everything before today
        rsi_today   = float(today_row["rsi14"])
    except (KeyError, ValueError, IndexError):
        return {"active": False, "rsi_today": None, "over_threshold_days": [],
                "threshold": threshold, "reason": "Could not parse RSI values"}

    # Condition 1: today's RSI > threshold
    if rsi_today <= threshold:
        return {
            "active":               False,
            "rsi_today":            rsi_today,
            "over_threshold_days":  [],
            "threshold":            threshold,
            "reason":               f"Today RSI {rsi_today:.1f} ≤ {threshold} — override not triggered",
        }

    # Condition 2: at least one prior day in the lookback window also exceeded threshold
    over_days = [r for r in prior_rows if _safe_float(r.get("rsi14")) > threshold]

    if not over_days:
        return {
            "active":               False,
            "rsi_today":            rsi_today,
            "over_threshold_days":  [],
            "threshold":            threshold,
            "reason":               (f"Today RSI {rsi_today:.1f} > {threshold} but no prior day "
                                     f"in last {len(prior_rows)} days exceeded threshold — "
                                     "treating as one-day spike, override not triggered"),
        }

    return {
        "active":               True,
        "rsi_today":            rsi_today,
        "over_threshold_days":  over_days,
        "threshold":            threshold,
        "reason":               (f"Today RSI {rsi_today:.1f} > {threshold} AND "
                                 f"{len(over_days)} of last {len(prior_rows)} days also exceeded "
                                 f"{threshold} — override ACTIVE"),
    }


def _safe_float(v) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


# ── CLI test ──────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    print("Fetching SPY RSI-14...")
    row = fetch_and_store()
    if row:
        print(f"  Today: RSI-14 = {row['rsi14']}  |  SPY close = {row['close']}")
    sig = get_rsi_signal()
    print(f"\nRSI Signal (10-day avg = {sig['avg_10d']}):")
    print(f"  Label:      {sig['signal']}")
    print(f"  Score adj:  {sig['score_adj']:+d}")
    print(f"\nLast {len(sig['history'])} days:")
    for r in sig["history"]:
        print(f"  {r['date']}  RSI={r['rsi14']}  SPY={r['close']}")
    override = check_rsi_override()
    print(f"\nRSI Override (threshold=76):")
    print(f"  Active:  {override['active']}")
    print(f"  Reason:  {override['reason']}")
