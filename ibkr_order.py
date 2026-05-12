#!/usr/bin/env python3
"""
ibkr_order.py — Places ETF orders in IBKR based on your Composer allocation JSON.

Reads the latest composer_allocations_*.json file, fetches current prices,
calculates shares for each ETF, and places orders via the IBKR Client Portal API.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  ONE-TIME SETUP (takes ~5 minutes)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  1. Download IBKR Client Portal API Gateway (free):
       https://www.interactivebrokers.com/en/index.php?f=5041
       → Scroll to "Client Portal API" → Download the ZIP

  2. Unzip to a folder, e.g.: C:\ClientPortal\

  3. Start the gateway (run Command Prompt as Administrator):
       cd C:\ClientPortal
       bin\run.bat root\conf.yaml

  4. Open a browser → go to: https://localhost:5000
       → Click "Advanced" → "Proceed" (self-signed cert warning is normal)
       → Log in with your IBKR credentials

  5. Leave the gateway running while you use this script.
     (You'll need to re-authenticate after ~24 hours.)

  6. Add your IBKR account number to composer_config.json:
       "ibkr_account": "U1234567"      ← replace with your actual account ID
       "ibkr_budget":  1000.0          ← optional; default 1000.0

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  USAGE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  python ibkr_order.py              ← DRY RUN (preview only, no real orders)
  python ibkr_order.py --live       ← place LIVE orders (asks confirmation)
  python ibkr_order.py --file composer_allocations_185_2026-05-11.json
  python ibkr_order.py --budget 500 ← override budget from command line
  python ibkr_order.py --fractional ← use fractional shares (must be enabled in IBKR)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  REQUIREMENTS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  pip install requests yfinance
"""

from __future__ import annotations

import argparse
import glob
import json
import sys
import time
import urllib3
from datetime import datetime
from pathlib import Path
from typing import Optional

import requests
import yfinance as yf

# Suppress SSL warning for localhost self-signed cert
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ── Paths ────────────────────────────────────────────────────────────────────
SCRIPT_DIR  = Path(__file__).resolve().parent
CONFIG_PATH = SCRIPT_DIR / "composer_config.json"

# ── IBKR Client Portal API base URL ─────────────────────────────────────────
IBKR_BASE = "https://localhost:5000/v1/api"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Config helpers
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def load_config() -> dict:
    if not CONFIG_PATH.exists():
        return {}
    try:
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Find latest Composer JSON
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def find_latest_json(directory: Path, pattern: str = "composer_allocations_*.json") -> Optional[Path]:
    """Return the most recently modified JSON matching the pattern."""
    matches = sorted(directory.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
    # Prefer files with actual date in name (not the generic 'composer_allocations_2026-*.json')
    # Files named with symphony ID (e.g. _185_) come first
    dated = [m for m in matches if any(c.isdigit() for c in m.stem.split("_")[-1])]
    return dated[0] if dated else (matches[0] if matches else None)


def load_allocation(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    return data


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Parse positions from JSON
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

CASH_SYMBOLS = {"$USD", "$CASH", "USD", "CASH"}

def parse_positions(data: dict) -> list[dict]:
    """
    Extract ETF positions from allocation JSON, skipping cash entries.
    Returns list of {ticker, weight_pct, composer_shares, composer_value}
    """
    positions = data.get("positions") or data.get("holdings") or []

    # Also try raw_api_entry > holdings
    if not positions and "raw_api_entry" in data:
        positions = data["raw_api_entry"].get("holdings", [])

    result = []
    for p in positions:
        ticker = p.get("ticker") or p.get("symbol", "")
        if not ticker or ticker.strip("$").upper() in CASH_SYMBOLS or ticker.startswith("$"):
            continue
        # Normalize weight: could be weight_pct (0-100) or allocation (0-1)
        weight = p.get("weight_pct") or p.get("allocation") or 0
        if weight and weight <= 1.5:          # looks like a 0-1 fraction
            weight = weight * 100
        result.append({
            "ticker":           ticker,
            "weight_pct":       float(weight),
            "composer_shares":  p.get("shares") or p.get("amount") or 0,
            "composer_value":   p.get("market_value") or p.get("value") or 0,
            "composer_price":   p.get("price") or 0,
        })

    # Renormalize so weights sum to 100
    total_w = sum(p["weight_pct"] for p in result)
    if total_w > 0 and abs(total_w - 100) > 0.5:
        for p in result:
            p["weight_pct"] = p["weight_pct"] / total_w * 100

    return result


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Price fetching (yfinance)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def fetch_prices_yfinance(tickers: list[str]) -> dict[str, float]:
    """Fetch latest prices from Yahoo Finance. Returns {ticker: price}."""
    print(f"\n  Fetching live prices from Yahoo Finance for: {', '.join(tickers)} ...")
    prices = {}
    for ticker in tickers:
        try:
            t = yf.Ticker(ticker)
            info = t.fast_info
            price = getattr(info, "last_price", None) or getattr(info, "regularMarketPrice", None)
            if price and price > 0:
                prices[ticker] = float(price)
                print(f"    {ticker:8s}  ${price:.4f}")
            else:
                print(f"    {ticker:8s}  ⚠ could not fetch price")
        except Exception as e:
            print(f"    {ticker:8s}  ⚠ error: {e}")
    return prices


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  IBKR Client Portal API
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class IBKRClient:
    """Thin wrapper around the IBKR Client Portal REST API (localhost:5000)."""

    def __init__(self, base_url: str = IBKR_BASE):
        self.base = base_url.rstrip("/")
        self.session = requests.Session()
        self.session.verify = False      # self-signed cert on localhost
        self.account_id: Optional[str] = None

    def get(self, path: str, **kwargs) -> dict:
        r = self.session.get(f"{self.base}/{path.lstrip('/')}", **kwargs)
        r.raise_for_status()
        return r.json()

    def post(self, path: str, payload: dict, **kwargs) -> dict | list:
        r = self.session.post(
            f"{self.base}/{path.lstrip('/')}",
            json=payload,
            **kwargs
        )
        r.raise_for_status()
        return r.json()

    # ── Auth ────────────────────────────────────────────────────────────────

    def check_auth(self) -> bool:
        """Returns True if the gateway is running and user is authenticated."""
        try:
            data = self.get("/iserver/auth/status")
            authenticated = data.get("authenticated", False)
            connected = data.get("connected", False)
            if not authenticated:
                print("\n  ⚠  IBKR gateway is running but you are NOT logged in.")
                print("     Open https://localhost:5000 in your browser and log in first.\n")
            return authenticated and connected
        except requests.exceptions.ConnectionError:
            print("\n  ✗  Cannot reach IBKR Client Portal Gateway at https://localhost:5000")
            print("     Make sure the gateway is running:")
            print("       cd C:\\ClientPortal")
            print("       bin\\run.bat root\\conf.yaml\n")
            return False
        except Exception as e:
            print(f"\n  ✗  Gateway error: {e}\n")
            return False

    def reauthenticate(self):
        """Tickle the session to prevent timeout."""
        try:
            self.post("/iserver/reauthenticate", {})
        except Exception:
            pass

    # ── Account ─────────────────────────────────────────────────────────────

    def get_accounts(self) -> list[str]:
        data = self.get("/iserver/accounts")
        return data.get("accounts", [])

    def get_account_summary(self, account_id: str) -> dict:
        return self.get(f"/portfolio/{account_id}/summary")

    def get_available_cash(self, account_id: str) -> float:
        """Return available cash (TotalCashValue) from account ledger."""
        try:
            ledger = self.get(f"/portfolio/{account_id}/ledger")
            # ledger is {currency: {cashbalance: ...}}
            base = ledger.get("BASE") or next(iter(ledger.values()), {})
            return float(base.get("cashbalance", 0))
        except Exception:
            return 0.0

    # ── Contract search (get conid) ──────────────────────────────────────────

    def search_contract(self, symbol: str) -> Optional[int]:
        """Find the IBKR contract ID (conid) for a US stock/ETF symbol."""
        try:
            results = self.get(f"/iserver/secdef/search?symbol={symbol}&name=false&secType=STK")
            # results is a list; find US exchange match
            for r in results:
                if r.get("ticker") == symbol or r.get("symbol") == symbol:
                    # Prefer SMART/NYSE/NASDAQ
                    conid = r.get("conid")
                    if conid:
                        return int(conid)
            if results:
                return int(results[0].get("conid", 0)) or None
        except Exception as e:
            print(f"    ⚠ Contract search failed for {symbol}: {e}")
        return None

    def resolve_conids(self, tickers: list[str]) -> dict[str, int]:
        """Return {ticker: conid} for all tickers."""
        print("\n  Looking up IBKR contract IDs ...")
        conids = {}
        for ticker in tickers:
            conid = self.search_contract(ticker)
            if conid:
                conids[ticker] = conid
                print(f"    {ticker:8s}  conid={conid}")
            else:
                print(f"    {ticker:8s}  ⚠ conid not found — will skip")
            time.sleep(0.3)   # be gentle with the API
        return conids

    # ── Live price from IBKR ─────────────────────────────────────────────────

    def fetch_prices_ibkr(self, conid_map: dict[str, int]) -> dict[str, float]:
        """Fetch live prices for conids from IBKR market data snapshot."""
        if not conid_map:
            return {}
        conid_list = ",".join(str(c) for c in conid_map.values())
        # field 31 = last price
        try:
            data = self.get(f"/iserver/marketdata/snapshot?conids={conid_list}&fields=31,84,86")
            prices = {}
            for item in (data if isinstance(data, list) else []):
                conid = str(item.get("conid", ""))
                price = item.get("31") or item.get("84")  # 31=last, 84=bid
                if price:
                    # price may come as string "93.67" or number
                    for ticker, cid in conid_map.items():
                        if str(cid) == conid:
                            try:
                                prices[ticker] = float(str(price).replace(",", ""))
                            except ValueError:
                                pass
            return prices
        except Exception as e:
            print(f"    ⚠ IBKR market data error: {e}")
            return {}

    # ── Place orders ─────────────────────────────────────────────────────────

    def place_orders(self, account_id: str, orders: list[dict]) -> list[dict]:
        """
        Submit a batch of orders.
        Each order dict: {conid, ticker, side, quantity, orderType, tif}
        Returns list of order responses.
        """
        ibkr_orders = []
        for o in orders:
            order = {
                "conid":     o["conid"],
                "orderType": o.get("orderType", "MKT"),
                "side":      o.get("side", "BUY"),
                "tif":       o.get("tif", "DAY"),
            }
            if o.get("use_cash_qty"):
                # Cash-quantity order: let IBKR calculate exact fractional shares
                order["cashQty"] = round(o["dollar_amount"], 2)
            else:
                order["quantity"] = o["quantity"]
                if o.get("fractional"):
                    order["quantity"] = round(o["quantity"], 4)
            ibkr_orders.append(order)

        payload = {"orders": ibkr_orders}
        try:
            resp = self.post(f"/iserver/account/{account_id}/orders", payload)
            # Response may be a list of {order_id, ...} or a reply-needed structure
            return resp if isinstance(resp, list) else [resp]
        except requests.exceptions.HTTPError as e:
            print(f"\n  ✗ Order submission failed: {e}")
            try:
                print(f"    Response: {e.response.text[:500]}")
            except Exception:
                pass
            return []

    def confirm_order_reply(self, reply_id: str, confirmed: bool = True) -> dict:
        """Some orders require a second confirmation (IBKR 'reply' flow)."""
        return self.post(f"/iserver/reply/{reply_id}", {"confirmed": confirmed})


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Order calculation
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def build_orders(
    positions: list[dict],
    prices: dict[str, float],
    conids: dict[str, int],
    budget: float,
    fractional: bool = False,
    use_cash_qty: bool = False,
) -> list[dict]:
    """
    Calculate orders from positions, prices, and budget.
    Returns list of order dicts ready for placement.
    """
    orders = []
    total_weight = sum(p["weight_pct"] for p in positions)

    for pos in positions:
        ticker = pos["ticker"]
        if ticker not in conids:
            print(f"  ⚠ Skipping {ticker} — no conid found")
            continue

        weight = pos["weight_pct"] / total_weight   # normalize to 0-1
        dollar_amount = budget * weight

        if dollar_amount < 1.0:
            print(f"  ⚠ Skipping {ticker} — allocation too small (${dollar_amount:.2f})")
            continue

        price = prices.get(ticker, 0)

        if use_cash_qty:
            # Let IBKR handle fractional shares via cash quantity
            quantity = dollar_amount / price if price > 0 else 0
            shares_display = quantity
        elif fractional:
            quantity = dollar_amount / price if price > 0 else 0
            shares_display = quantity
        else:
            # Whole shares only
            quantity = int(dollar_amount / price) if price > 0 else 0
            shares_display = quantity

        if quantity <= 0:
            print(f"  ⚠ Skipping {ticker} — quantity is 0 (price=${price:.2f}, budget=${dollar_amount:.2f})")
            continue

        orders.append({
            "ticker":        ticker,
            "conid":         conids[ticker],
            "side":          "BUY",
            "orderType":     "MKT",
            "tif":           "DAY",
            "weight_pct":    pos["weight_pct"],
            "dollar_amount": dollar_amount,
            "price":         price,
            "quantity":      shares_display,
            "fractional":    fractional,
            "use_cash_qty":  use_cash_qty,
        })

    return orders


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Display helpers
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def print_preview(orders: list[dict], budget: float, account_id: str, dry_run: bool):
    mode_label = "DRY RUN — NO ORDERS WILL BE PLACED" if dry_run else "⚡ LIVE ORDER PREVIEW"
    print()
    print("=" * 66)
    print(f"  {mode_label}")
    print(f"  Account : {account_id}")
    print(f"  Budget  : ${budget:,.2f}")
    print(f"  Time    : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 66)
    print(f"  {'Ticker':<8}  {'Weight':>7}  {'Price':>9}  {'Shares':>10}  {'$ Amount':>10}")
    print(f"  {'-'*8}  {'-'*7}  {'-'*9}  {'-'*10}  {'-'*10}")

    total_spend = 0
    for o in orders:
        shares_fmt = f"{o['quantity']:.4f}" if o.get("fractional") or o.get("use_cash_qty") else f"{int(o['quantity'])}"
        print(
            f"  {o['ticker']:<8}  {o['weight_pct']:>6.2f}%  "
            f"${o['price']:>8.4f}  {shares_fmt:>10}  ${o['dollar_amount']:>9.2f}"
        )
        total_spend += o["dollar_amount"]

    print(f"  {'-'*8}  {'-'*7}  {'-'*9}  {'-'*10}  {'-'*10}")
    print(f"  {'TOTAL':<8}  {'':>7}  {'':>9}  {'':>10}  ${total_spend:>9.2f}")
    print("=" * 66)
    remaining = budget - total_spend
    print(f"  Remaining cash (approx): ${remaining:.2f}")
    print()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Main
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def main():
    parser = argparse.ArgumentParser(description="Place ETF orders in IBKR from Composer allocation JSON.")
    parser.add_argument("--live",       action="store_true", help="Place real orders (default: dry run)")
    parser.add_argument("--fractional", action="store_true", help="Use fractional shares (must be enabled in your IBKR account)")
    parser.add_argument("--cash-qty",   action="store_true", dest="cash_qty",
                        help="Use IBKR cash-quantity orders (fractional shares via dollar amount)")
    parser.add_argument("--budget",     type=float, default=None, help="Override budget in USD")
    parser.add_argument("--file",       type=str,   default=None, help="Specific JSON file to use")
    parser.add_argument("--account",    type=str,   default=None, help="Override IBKR account ID")
    args = parser.parse_args()

    dry_run = not args.live

    # ── Load config ──────────────────────────────────────────────────────────
    config = load_config()
    budget = args.budget or config.get("ibkr_budget", 1000.0)
    account_id_cfg = args.account or config.get("ibkr_account", "")

    print()
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("  IBKR ETF Order Placer  —  powered by Composer allocation")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

    # ── Find and load JSON ───────────────────────────────────────────────────
    if args.file:
        json_path = Path(args.file)
        if not json_path.is_absolute():
            json_path = SCRIPT_DIR / json_path
    else:
        json_path = find_latest_json(SCRIPT_DIR)

    if not json_path or not json_path.exists():
        print(f"\n  ✗ No Composer allocation JSON found in {SCRIPT_DIR}")
        print("    Run composer_pull_allocation.py first, or pass --file <path>")
        sys.exit(1)

    print(f"\n  Allocation file : {json_path.name}")
    data = load_allocation(json_path)
    positions = parse_positions(data)

    if not positions:
        print("  ✗ No ETF positions found in JSON (only cash?). Exiting.")
        sys.exit(1)

    date_str = data.get("date", "unknown date")
    symphony_name = data.get("symphony_name", "")
    print(f"  Symphony        : {symphony_name or '—'}")
    print(f"  Date            : {date_str}")
    print(f"  ETFs found      : {', '.join(p['ticker'] for p in positions)}")
    print(f"  Budget          : ${budget:,.2f}")
    print(f"  Mode            : {'⚡ LIVE' if not dry_run else 'DRY RUN'}")

    tickers = [p["ticker"] for p in positions]

    # ── Connect to IBKR gateway ──────────────────────────────────────────────
    ibkr = IBKRClient()
    print("\n  Connecting to IBKR Client Portal Gateway ...")

    gateway_ok = ibkr.check_auth()
    if not gateway_ok:
        if dry_run:
            print("  (Dry-run mode: continuing with Yahoo Finance prices only.)")
            print("  (Contract IDs will be skipped — order quantities are estimates.)\n")
            # Fall through with fake conids for preview
            prices = fetch_prices_yfinance(tickers)
            fake_conids = {t: 0 for t in tickers if t in prices}
            orders = build_orders(
                positions, prices, fake_conids, budget,
                fractional=args.fractional or args.cash_qty,
                use_cash_qty=args.cash_qty,
            )
            print_preview(orders, budget, account_id_cfg or "N/A (dry run)", dry_run=True)
            print("  To place real orders:")
            print("  1. Start the IBKR Client Portal Gateway (see setup instructions at top of script)")
            print("  2. Authenticate at https://localhost:5000")
            print("  3. Run:  python ibkr_order.py --live")
            return
        else:
            print("  ✗ Cannot place live orders without gateway. Exiting.")
            sys.exit(1)

    print("  ✓ Gateway connected and authenticated")
    ibkr.reauthenticate()

    # ── Resolve account ID ───────────────────────────────────────────────────
    accounts = ibkr.get_accounts()
    if not accounts:
        print("\n  ✗ No accounts found via IBKR API. Check your login.")
        sys.exit(1)

    if account_id_cfg and account_id_cfg in accounts:
        account_id = account_id_cfg
    elif account_id_cfg:
        print(f"\n  ⚠ Account {account_id_cfg!r} from config not found in gateway.")
        print(f"    Available accounts: {accounts}")
        account_id = accounts[0]
        print(f"    Using first account: {account_id}")
    else:
        account_id = accounts[0]

    print(f"  Account         : {account_id}")

    # ── Check available cash ─────────────────────────────────────────────────
    available_cash = ibkr.get_available_cash(account_id)
    print(f"  Available cash  : ${available_cash:,.2f}")
    if available_cash > 0 and available_cash < budget:
        print(f"\n  ⚠  Budget (${budget:,.2f}) exceeds available cash (${available_cash:,.2f})")
        print(f"     Reducing budget to ${available_cash:.2f}")
        budget = available_cash * 0.995   # leave ~0.5% buffer for fees

    # ── Resolve conids ───────────────────────────────────────────────────────
    conids = ibkr.resolve_conids(tickers)
    if not conids:
        print("\n  ✗ Could not resolve any contract IDs. Check symbol names.")
        sys.exit(1)

    # ── Fetch prices ─────────────────────────────────────────────────────────
    print("\n  Fetching live prices from IBKR market data ...")
    # First snapshot call sometimes returns empty; retry once
    prices = ibkr.fetch_prices_ibkr(conids)
    if len(prices) < len(conids):
        time.sleep(2)
        prices.update(ibkr.fetch_prices_ibkr(conids))

    # Fill any missing prices from yfinance
    missing = [t for t in tickers if t not in prices or prices[t] <= 0]
    if missing:
        print(f"  Filling missing prices from Yahoo Finance: {missing}")
        yf_prices = fetch_prices_yfinance(missing)
        prices.update(yf_prices)

    if not prices:
        print("\n  ✗ Could not fetch any prices. Exiting.")
        sys.exit(1)

    for ticker in tickers:
        p = prices.get(ticker, 0)
        status = f"${p:.4f}" if p > 0 else "⚠ no price"
        print(f"    {ticker:8s}  {status}")

    # ── Build orders ─────────────────────────────────────────────────────────
    orders = build_orders(
        positions, prices, conids, budget,
        fractional=args.fractional or args.cash_qty,
        use_cash_qty=args.cash_qty,
    )

    if not orders:
        print("\n  ✗ No valid orders to place. Check prices and budget.")
        sys.exit(1)

    # ── Preview ──────────────────────────────────────────────────────────────
    print_preview(orders, budget, account_id, dry_run=dry_run)

    if dry_run:
        print("  This is a DRY RUN — no orders were placed.")
        print("  Run with --live to place real orders.")
        return

    # ── Confirm before live orders ────────────────────────────────────────────
    print("  ⚠  You are about to place LIVE orders with REAL money.")
    confirm = input("  Type 'YES' to confirm and place orders: ").strip()
    if confirm != "YES":
        print("  Cancelled — no orders placed.")
        return

    # ── Place orders ─────────────────────────────────────────────────────────
    print("\n  Submitting orders to IBKR ...")
    responses = ibkr.place_orders(account_id, orders)

    print()
    order_ids = []
    for resp in responses:
        if isinstance(resp, dict):
            if resp.get("id") or resp.get("order_id"):
                oid = resp.get("id") or resp.get("order_id")
                order_ids.append(oid)
                print(f"  ✓ Order placed — ID: {oid}")
            elif resp.get("message") or resp.get("error"):
                msg = resp.get("message") or resp.get("error")
                print(f"  ⚠ Response: {msg}")
                # Some orders need a reply confirmation
                if resp.get("id"):
                    ibkr.confirm_order_reply(resp["id"])
            else:
                print(f"  → {resp}")

    if order_ids:
        print(f"\n  ✓ {len(order_ids)} order(s) submitted successfully.")
        print(f"  Check your IBKR account or TWS to monitor fills.")
    else:
        print("\n  ⚠ No order IDs returned. Check IBKR portal for order status.")


if __name__ == "__main__":
    main()
