"""
ibkr_trader.py — BLEE Quant Analytics / IBKR Auto-Trader
══════════════════════════════════════════════════════════
Reads today's allocation from index2.html, connects to Interactive Brokers
via IB Gateway, detects whether the allocation changed since last run, and
places GTC limit orders when a rebalance is needed.

SETUP (one-time):
  1. Download & install IB Gateway:
       https://www.interactivebrokers.com/en/trading/ibgateway-stable.php
  2. Launch IB Gateway → choose "Paper Trading" → log in with your IBKR
     credentials.  Leave it running in the background.
  3. In IB Gateway: Configure → Settings → API → Enable ActiveX and Socket Clients
       Port: 4002 (paper) — already the default
       ✓ Allow connections from localhost only
  4. Install Python packages (run once in PowerShell):
       pip install ib_insync yfinance --break-system-packages
  5. Enable Fractional Shares in your live account:
       IBKR Account Management → Trading → Fractional Shares → Enable

SWITCHING TO LIVE:
  Change  MODE = "paper"  →  MODE = "live"  below.
  Live account (U25734106) uses IB Gateway on port 4001.

DAILY WORKFLOW:
  • Run composer_pull_allocation.py first (updates index2.html with today's signal)
  • Then run:  python ibkr_trader.py
  • If allocation unchanged → script exits without placing orders
  • If changed → cancels stale open orders, places new GTC limit orders
"""

# ── Configuration ─────────────────────────────────────────────────────────────

MODE           = "live"           # "paper" or "live"
LIVE_ACCOUNT   = "U25734106"
STARTING_CASH  = 500.00           # used only if no prior portfolio value on file

# TWS ports (7497=paper, 7496=live)
# IB Gateway ports (4002=paper, 4001=live) — use if running Gateway instead of TWS
_PORTS = {"paper": 7497, "live": 7496}
IB_HOST        = "127.0.0.1"
IB_PORT        = _PORTS[MODE]
IB_CLIENT_ID   = 10               # any unique integer; change if conflict

# Order settings
LIMIT_BUY_SLIP   = 0.002          # +0.2% above close → improves overnight fill probability
LIMIT_SELL_SLIP  = 0.002          # −0.2% below close
MIN_ORDER_USD    = 1.00           # skip orders smaller than this (avoids tiny adjustments)
CASH_BUFFER_PCT  = 0.005          # keep 0.5% cash buffer to cover fees / rounding
USE_FRACTIONAL   = False           # True  = send fractional qty (requires account feature)
                                   # False = round DOWN to whole shares (safe fallback)
ORDER_SETTLE_SEC = 8              # seconds to wait for IBKR to confirm / reject each order

# Paths (all in the same folder as this script)
from pathlib import Path
SCRIPT_DIR        = Path(__file__).parent
INDEX2_HTML       = SCRIPT_DIR / "index2.html"
TRADE_LOG_CSV     = SCRIPT_DIR / "ibkr_trade_log.csv"
LAST_ALLOC_JSON   = SCRIPT_DIR / "ibkr_last_allocation.json"

# ── Imports ───────────────────────────────────────────────────────────────────
import asyncio
import csv
import datetime as dt
import json
import logging
import re
import sys
import time

# ── Windows / Python 3.10+ asyncio fix (required by ib_insync) ───────────────
if sys.platform == "win32":
    asyncio.set_event_loop(asyncio.new_event_loop())

log = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)

# ── 1. Parse today's allocation from index2.html ──────────────────────────────

def parse_index2_allocation() -> dict:
    """
    Extract the JS `const DATA = {...};` block from index2.html and parse it.
    Returns dict with keys: today_allocations, symphony_name, last_updated, etc.
    Raises RuntimeError if the file cannot be parsed.
    """
    if not INDEX2_HTML.exists():
        raise RuntimeError(f"index2.html not found at {INDEX2_HTML}")

    html = INDEX2_HTML.read_text(encoding="utf-8")
    m = re.search(r"const DATA\s*=\s*(\{.*?\});", html, re.DOTALL)
    if not m:
        raise RuntimeError("Could not locate `const DATA = {...}` block in index2.html")

    import json as _json
    try:
        data = _json.loads(m.group(1))
    except _json.JSONDecodeError as e:
        raise RuntimeError(f"JSON parse error in DATA block: {e}")

    allocs = data.get("today_allocations", [])
    if not allocs:
        raise RuntimeError("today_allocations is empty in index2.html — run composer_pull_allocation.py first")

    return data


def allocation_signature(allocs: list[dict]) -> dict:
    """Return {ticker: round(weight,1)} for change-detection comparison."""
    return {a["ticker"]: round(float(a["weight_pct"]), 1)
            for a in allocs if float(a.get("weight_pct", 0)) > 0}


# ── 2. Last-allocation state file ─────────────────────────────────────────────

def load_last_allocation() -> dict | None:
    if not LAST_ALLOC_JSON.exists():
        return None
    try:
        return json.loads(LAST_ALLOC_JSON.read_text())
    except Exception:
        return None


def save_last_allocation(sig: dict, portfolio_value: float) -> None:
    payload = {"allocation": sig, "portfolio_value": portfolio_value,
               "saved_at": dt.datetime.now().isoformat()}
    LAST_ALLOC_JSON.write_text(json.dumps(payload, indent=2))


def allocation_changed(current_sig: dict) -> bool:
    last = load_last_allocation()
    if last is None:
        log.info("No prior allocation on file — treating as first run.")
        return True
    prev_sig = last.get("allocation", {})
    if prev_sig == current_sig:
        log.info(f"Allocation unchanged vs last run: {current_sig}")
        return False
    log.info(f"Allocation changed.\n  Previous: {prev_sig}\n  Current:  {current_sig}")
    return True


# ── 3. Fetch last close prices via yfinance ───────────────────────────────────

def fetch_prices(tickers: list[str]) -> dict[str, float]:
    """Return {ticker: last_close} for all tickers."""
    try:
        import yfinance as yf
    except ImportError:
        raise RuntimeError("yfinance not installed. Run: pip install yfinance --break-system-packages")

    prices = {}
    for ticker in tickers:
        try:
            df = yf.download(ticker, period="5d", progress=False, auto_adjust=True)
            # yfinance 1.x may return MultiIndex columns when downloading single ticker
            close = df["Close"]
            if hasattr(close, "columns"):          # MultiIndex — squeeze to Series
                close = close.iloc[:, 0]
            price = float(close.dropna().iloc[-1])
            prices[ticker] = round(price, 4)
            log.info(f"  {ticker:6s}  last price = ${prices[ticker]:,.4f}")
        except Exception as e:
            raise RuntimeError(f"Could not fetch price for {ticker}: {e}")

    return prices


# ── 4. IBKR connection ────────────────────────────────────────────────────────

def connect_ibkr():
    try:
        from ib_insync import IB
    except ImportError:
        raise RuntimeError(
            "ib_insync not installed.\n"
            "Run:  pip install ib_insync --break-system-packages"
        )

    ib = IB()
    log.info(f"Connecting to IB Gateway ({MODE}) at {IB_HOST}:{IB_PORT} ...")
    try:
        ib.connect(IB_HOST, IB_PORT, clientId=IB_CLIENT_ID, timeout=15)
    except Exception as e:
        raise RuntimeError(
            f"Could not connect to IB Gateway on port {IB_PORT}.\n"
            f"  → Make sure IB Gateway is running and logged in ({MODE} mode).\n"
            f"  → Error: {e}"
        )
    log.info(f"Connected. Account(s): {ib.managedAccounts()}")
    return ib


def get_account_id(ib) -> str:
    """Return the account ID to use for this session."""
    accounts = ib.managedAccounts()
    if MODE == "live" and LIVE_ACCOUNT in accounts:
        return LIVE_ACCOUNT
    if accounts:
        return accounts[0]
    raise RuntimeError("No managed accounts found in IB Gateway session.")


def get_portfolio_value(ib, account_id: str) -> float:
    """
    Return total net liquidation value of the account.
    ib_insync auto-subscribes to account data on connect — just read it directly.
    Falls back to STARTING_CASH if value cannot be determined.
    """
    # ib_insync downloads account data automatically on connection
    time.sleep(2)  # allow data to arrive

    for av in ib.accountValues(account_id):
        if av.tag == "NetLiquidation" and av.currency == "USD":
            val = float(av.value)
            log.info(f"Account {account_id}  NetLiquidation = ${val:,.2f}")
            return val

    # Fallback: sum position market values + cash
    log.warning("NetLiquidation not found — using STARTING_CASH as portfolio value.")
    return STARTING_CASH


def get_current_positions(ib, account_id: str) -> dict[str, float]:
    """Return {ticker: shares_held} for the account."""
    positions = {}
    for pos in ib.positions(account_id):
        ticker = pos.contract.symbol
        positions[ticker] = pos.position
    log.info(f"Current positions: {positions}")
    return positions


def cancel_open_orders(ib, account_id: str, tickers: set[str]) -> None:
    """Cancel any open GTC orders for the given tickers (stale from prior run)."""
    cancelled = []
    for trade in ib.openTrades():
        if (trade.order.account == account_id and
                trade.contract.symbol in tickers and
                trade.order.tif == "GTC"):
            ib.cancelOrder(trade.order)
            cancelled.append(trade.contract.symbol)
            log.info(f"  Cancelled stale GTC order: {trade.contract.symbol}")
    if not cancelled:
        log.info("  No stale GTC orders to cancel.")


# ── 5. Build and place orders ─────────────────────────────────────────────────

def build_orders(
    allocs: list[dict],
    prices: dict[str, float],
    current_positions: dict[str, float],
    portfolio_value: float,
) -> list[dict]:
    """
    Compare target allocations with current positions.
    Returns list of order dicts:
      {ticker, action, qty, limit_price, target_pct, target_value}
    """
    usable_cash = portfolio_value * (1 - CASH_BUFFER_PCT)
    orders = []

    # Build a set of tickers we currently hold but are NOT in today's allocation
    target_tickers = {a["ticker"] for a in allocs if float(a.get("weight_pct", 0)) > 0}
    exit_tickers   = set(current_positions) - target_tickers

    # ── Sells first: exit positions no longer in allocation ──────────────────
    for ticker in exit_tickers:
        current_shares = current_positions.get(ticker, 0)
        if current_shares <= 0:
            continue
        price = prices.get(ticker)
        if not price:
            log.warning(f"  No price for {ticker} — skipping sell")
            continue
        limit = round(price * (1 - LIMIT_SELL_SLIP), 2)
        order_value = current_shares * price
        if order_value < MIN_ORDER_USD:
            log.info(f"  {ticker}: sell value ${order_value:.2f} < min — skipping")
            continue
        orders.append({
            "ticker":       ticker,
            "action":       "SELL",
            "qty":          round(current_shares, 6),
            "limit_price":  limit,
            "target_pct":   0.0,
            "target_value": 0.0,
        })
        log.info(f"  SELL {current_shares:.4f} {ticker} @ ${limit:.2f} (exit)")

    # ── Buys / rebalances ────────────────────────────────────────────────────
    for alloc in allocs:
        ticker     = alloc["ticker"]
        weight_pct = float(alloc.get("weight_pct", 0))
        if weight_pct <= 0:
            continue

        price = prices.get(ticker)
        if not price:
            log.warning(f"  No price for {ticker} — skipping")
            continue

        target_value   = usable_cash * weight_pct / 100.0
        current_shares = current_positions.get(ticker, 0.0)
        current_value  = current_shares * price
        delta_value    = target_value - current_value
        delta_shares   = delta_value / price

        if abs(delta_value) < MIN_ORDER_USD:
            log.info(f"  {ticker}: Δ${delta_value:+.2f} < min — no order needed")
            continue

        action = "BUY" if delta_shares > 0 else "SELL"
        slip   = LIMIT_BUY_SLIP if action == "BUY" else -LIMIT_SELL_SLIP
        limit  = round(price * (1 + slip), 2)

        raw_qty = abs(delta_shares)
        if USE_FRACTIONAL:
            qty = round(raw_qty, 6)
        else:
            qty = float(round(raw_qty))  # round to nearest whole share (0.5+ rounds up)
            if qty < 1:
                log.info(f"  {ticker}: rounds to 0 whole shares (${abs(delta_value):.2f} target, ${price:.2f}/share) — skipping")
                continue

        orders.append({
            "ticker":       ticker,
            "action":       action,
            "qty":          qty,
            "limit_price":  limit,
            "target_pct":   weight_pct,
            "target_value": round(target_value, 2),
        })
        log.info(
            f"  {action} {qty:.4f} {ticker} @ ${limit:.2f}  "
            f"(target {weight_pct:.1f}% = ${target_value:.2f}  "
            f"current ${current_value:.2f}  Δ${delta_value:+.2f})"
        )

    return orders


def place_orders(ib, account_id: str, orders: list[dict]) -> list[dict]:
    """
    Place GTC limit orders via ib_insync.
    Waits up to ORDER_SETTLE_SEC seconds for IBKR to confirm or reject each order,
    so the returned status accurately reflects Cancelled / Filled / Submitted.
    Returns enriched order list with order_id and status fields.
    """
    from ib_insync import Stock, LimitOrder

    # States that indicate IBKR has finished processing (terminal or stable)
    SETTLED = {"Submitted", "PreSubmitted", "Filled",
                "Cancelled", "Inactive", "ApiCancelled"}

    placed = []
    errors_seen: list[str] = []

    def _on_error(reqId, errorCode, errorString, contract):
        if errorCode in (10243, 201, 321, 103):  # fractional / order-rejected errors
            errors_seen.append(f"Error {errorCode}: {errorString}")

    ib.errorEvent += _on_error

    for o in orders:
        ticker = o["ticker"]
        errors_seen.clear()
        try:
            contract = Stock(ticker, "SMART", "USD")
            ib.qualifyContracts(contract)

            ibkr_order = LimitOrder(
                action        = o["action"],
                totalQuantity = o["qty"],
                lmtPrice      = o["limit_price"],
                tif           = "GTC",
                account       = account_id,
            )

            trade    = ib.placeOrder(contract, ibkr_order)
            order_id = trade.order.orderId

            # ── Poll until IBKR settles the order or timeout ──────────────────
            deadline = time.time() + ORDER_SETTLE_SEC
            while time.time() < deadline:
                ib.sleep(0.5)
                status = trade.orderStatus.status
                if status in SETTLED or errors_seen:
                    break

            status = trade.orderStatus.status or "PendingSubmit"

            # If IBKR sent back an error callback, override status to Cancelled
            if errors_seen:
                status = "Cancelled"
                err_msg = errors_seen[-1]
                log.error(f"  ✗ {o['action']} {o['qty']:.4f} {ticker} REJECTED — {err_msg}")
                placed.append({**o, "order_id": order_id, "status": f"Cancelled: {err_msg}"})
                continue

            icon = "✓" if status not in ("Cancelled", "Inactive", "ApiCancelled") else "✗"
            log.info(f"  {icon} {o['action']} {o['qty']:.4f} {ticker} "
                     f"@ ${o['limit_price']:.2f}  GTC  orderId={order_id}  status={status}")

            placed.append({**o, "order_id": order_id, "status": status})

        except Exception as e:
            log.error(f"  ✗ Failed to place order for {ticker}: {e}")
            placed.append({**o, "order_id": None, "status": f"ERROR: {e}"})

    ib.errorEvent -= _on_error
    return placed


# ── 6. Trade log ──────────────────────────────────────────────────────────────

LOG_HEADER = [
    "date", "run_datetime", "mode", "account",
    "portfolio_value", "ticker", "action",
    "target_pct", "target_value",
    "qty_shares", "limit_price",
    "order_id", "status",
]


def append_trade_log(rows: list[dict], portfolio_value: float, account_id: str) -> None:
    now_str = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    today   = dt.date.today().isoformat()

    write_header = not TRADE_LOG_CSV.exists()
    with open(TRADE_LOG_CSV, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=LOG_HEADER, extrasaction="ignore")
        if write_header:
            w.writeheader()
        for row in rows:
            w.writerow({
                "date":            today,
                "run_datetime":    now_str,
                "mode":            MODE,
                "account":         account_id,
                "portfolio_value": round(portfolio_value, 2),
                "ticker":          row["ticker"],
                "action":          row["action"],
                "target_pct":      row.get("target_pct", 0),
                "target_value":    row.get("target_value", 0),
                "qty_shares":      row.get("qty", 0),
                "limit_price":     row.get("limit_price", 0),
                "order_id":        row.get("order_id", ""),
                "status":          row.get("status", ""),
            })
    log.info(f"Trade log updated: {TRADE_LOG_CSV}  ({len(rows)} rows appended)")


def log_no_change(portfolio_value: float, account_id: str, sig: dict) -> None:
    """Write a single HOLD row to the log when no rebalance is needed."""
    now_str = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    today   = dt.date.today().isoformat()

    write_header = not TRADE_LOG_CSV.exists()
    with open(TRADE_LOG_CSV, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=LOG_HEADER, extrasaction="ignore")
        if write_header:
            w.writeheader()
        for ticker, pct in sig.items():
            w.writerow({
                "date":            today,
                "run_datetime":    now_str,
                "mode":            MODE,
                "account":         account_id,
                "portfolio_value": round(portfolio_value, 2),
                "ticker":          ticker,
                "action":          "HOLD",
                "target_pct":      pct,
                "target_value":    "",
                "qty_shares":      "",
                "limit_price":     "",
                "order_id":        "",
                "status":          "no change",
            })
    log.info(f"Logged HOLD (no-change day) to {TRADE_LOG_CSV}")


# ── 7. Main ───────────────────────────────────────────────────────────────────

def main() -> int:
    log.info(f"═══ IBKR Auto-Trader  mode={MODE.upper()}  ═══")

    # ── Step 1: Parse today's allocation ──────────────────────────────────────
    log.info("Step 1: Reading allocation from index2.html ...")
    try:
        data   = parse_index2_allocation()
    except RuntimeError as e:
        log.error(str(e))
        return 1

    allocs      = [a for a in data["today_allocations"] if float(a.get("weight_pct", 0)) > 0]
    current_sig = allocation_signature(allocs)
    log.info(f"Today's allocation: {current_sig}")

    symphony = data.get("symphony_name", "")
    log.info(f"Symphony: {symphony}")

    # ── Step 2: Check if allocation changed ───────────────────────────────────
    log.info("Step 2: Checking for allocation change ...")
    changed = allocation_changed(current_sig)

    # ── Step 3: Connect to IB Gateway ─────────────────────────────────────────
    log.info("Step 3: Connecting to IB Gateway ...")
    try:
        ib = connect_ibkr()
    except RuntimeError as e:
        log.error(str(e))
        return 1

    account_id = get_account_id(ib)
    log.info(f"Using account: {account_id}")

    # ── Step 4: Get portfolio value and positions ──────────────────────────────
    log.info("Step 4: Fetching account data ...")
    portfolio_value   = get_portfolio_value(ib, account_id)
    current_positions = get_current_positions(ib, account_id)

    # ── Step 5: No-change day → log and exit ──────────────────────────────────
    if not changed:
        log.info("Allocation unchanged — no rebalance needed today.")
        log_no_change(portfolio_value, account_id, current_sig)
        save_last_allocation(current_sig, portfolio_value)
        ib.disconnect()
        return 0

    # ── Step 6: Fetch prices ───────────────────────────────────────────────────
    all_tickers = list(set(current_sig.keys()) | set(current_positions.keys()))
    log.info(f"Step 6: Fetching prices for {sorted(all_tickers)} ...")
    try:
        prices = fetch_prices(sorted(all_tickers))
    except RuntimeError as e:
        log.error(str(e))
        ib.disconnect()
        return 1

    # ── Step 7: Build order list ───────────────────────────────────────────────
    log.info("Step 7: Building order plan ...")
    orders = build_orders(allocs, prices, current_positions, portfolio_value)

    if not orders:
        log.info("No orders to place (all positions within threshold).")
        log_no_change(portfolio_value, account_id, current_sig)
        save_last_allocation(current_sig, portfolio_value)
        ib.disconnect()
        return 0

    # ── Step 8: Show order summary and confirm ─────────────────────────────────
    print("\n" + "═" * 60)
    print(f"  MODE:      {MODE.upper()}")
    print(f"  Account:   {account_id}")
    print(f"  Portfolio: ${portfolio_value:,.2f}")
    print(f"  Orders to place ({len(orders)}):")
    for o in orders:
        print(f"    {o['action']:4s}  {o['qty']:.4f} {o['ticker']:6s}  "
              f"limit ${o['limit_price']:.2f}  "
              f"(≈${o['qty']*o['limit_price']:.2f})")
    print("═" * 60)

    confirm = input("\nProceed? [y/N] → ").strip().lower()
    if confirm != "y":
        log.info("Aborted by user.")
        ib.disconnect()
        return 0

    # ── Step 9: Cancel stale GTC orders for these tickers ─────────────────────
    log.info("Step 9: Cancelling stale GTC orders ...")
    cancel_open_orders(ib, account_id, {o["ticker"] for o in orders})
    time.sleep(1)

    # ── Step 10: Place new orders ──────────────────────────────────────────────
    log.info("Step 10: Placing GTC limit orders ...")
    placed = place_orders(ib, account_id, orders)

    # ── Step 11: Record trades ─────────────────────────────────────────────────
    log.info("Step 11: Recording trades ...")
    append_trade_log(placed, portfolio_value, account_id)
    save_last_allocation(current_sig, portfolio_value)

    ib.disconnect()
    log.info("═══ Done ═══")

    # ── Print summary ──────────────────────────────────────────────────────────
    _bad = {"Cancelled", "Inactive", "ApiCancelled", "ERROR"}
    success = [o for o in placed
               if not any(b in str(o.get("status", "")) for b in _bad)]
    failed  = [o for o in placed
               if any(b in str(o.get("status", "")) for b in _bad)]
    print(f"\n✓ {len(success)} orders live  |  ✗ {len(failed)} rejected/errors")
    if failed:
        for o in failed:
            print(f"  ✗ {o['ticker']}: {o['status']}")
    if failed and "Cancelled: Error 10243" in str([o.get("status") for o in failed]):
        print("\n  ⚠  Error 10243 = Fractional shares not enabled on this account.")
        print("     Fix: IBKR Client Portal → Settings → Trading → Fractional Shares → Enable")
        print("     Or set  USE_FRACTIONAL = False  in ibkr_trader.py to use whole shares only.")
    print(f"\nTrade log: {TRADE_LOG_CSV}")

    return 0 if not failed else 2


# ── CLI ───────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    sys.exit(main())
