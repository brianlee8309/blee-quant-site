#!/usr/bin/env python3
"""
Composer Trading - Daily Symphony ETF Allocation Puller

Reads API credentials and Symphony ID from `composer_config.json` (located
next to this script), calls the Composer Trader API, and appends today's
ETF distribution to a CSV log.

API reference:
    Base URL : https://api.composer.trade
    Docs     : https://api.composer.trade/docs/
    Auth     : two headers
                   x-api-key-id:   <your key id>
                   authorization:  Bearer <your key secret>

Config file (in the same folder as this script):
    composer_config.json
    {
        "api_key":      "c6060860-bbe2-4ada-bc3d-a5f2d49a14d9",
        "api_secret":   "0f3bdefd-b2fa-417d-8e5c-4423aae85bcd",
        "symphony_id":  "<symphony id, e.g. yrsRTIwEWPQpoZOWArGm>",
        "account_uuid": "<optional; auto-discovered if omitted>"
    }

Outputs (in the same folder as this script):
    composer_allocations.csv          -- one row per ETF per day (cumulative)
    composer_raw_<YYYY-MM-DD>.json    -- raw API response for that day
    composer_run.log                  -- run log

Run manually:
    python3 composer_pull_allocation.py        (macOS / Linux)
    python  composer_pull_allocation.py        (Windows)
"""

from __future__ import annotations

import csv
import datetime as dt
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

# ---- Paths (script-relative so it works on any machine) --------------------
SCRIPT_DIR  = Path(__file__).resolve().parent
CONFIG_PATH = SCRIPT_DIR / "composer_config.json"
LOG_PATH    = SCRIPT_DIR / "composer_run.log"
# Per-symphony CSV / HTML paths are resolved at runtime from the config.

# ---- Composer API -----------------------------------------------------------
API_BASE = "https://api.composer.trade"


def log(msg: str) -> None:
    ts = dt.datetime.now().isoformat(timespec="seconds")
    line = f"[{ts}] {msg}"
    print(line)
    with open(LOG_PATH, "a") as f:
        f.write(line + "\n")


def load_config() -> dict:
    if not CONFIG_PATH.exists():
        log(f"ERROR: config file not found at {CONFIG_PATH}")
        sys.exit(1)
    with open(CONFIG_PATH) as f:
        cfg = json.load(f)
    for k in ("api_key", "api_secret"):
        if not cfg.get(k):
            log(f"ERROR: '{k}' missing from config")
            sys.exit(1)
    if not cfg.get("symphonies") and not cfg.get("symphony_id"):
        log("ERROR: config must have either 'symphonies' (list) or 'symphony_id' (legacy)")
        sys.exit(1)
    return cfg


def _resolve_symphonies(cfg: dict) -> list[dict]:
    """
    Return a normalized list of {id, name, csv, html} dicts.
    Supports the new `symphonies: [...]` format and the legacy single
    `symphony_id` config.
    """
    out: list[dict] = []
    if isinstance(cfg.get("symphonies"), list) and cfg["symphonies"]:
        for entry in cfg["symphonies"]:
            sid = entry.get("id") or entry.get("symphony_id")
            if not sid:
                continue
            out.append({
                "id":   sid,
                "name": entry.get("name") or "",
                "csv":  entry.get("csv")  or f"composer_allocations_{sid[:8]}.csv",
                "html": entry.get("html") or f"index_{sid[:8]}.html",
            })
        return out
    sid = cfg.get("symphony_id") or ""
    if sid:
        out.append({
            "id":   sid,
            "name": "",
            "csv":  "composer_allocations.csv",
            "html": "index.html",
        })
    return out


def api_request(cfg: dict, method: str, path: str, body: dict | None = None) -> dict:
    """
    Call the Composer Trader API.
    Auth: x-api-key-id + authorization: Bearer <secret>
    """
    body_str = json.dumps(body, separators=(",", ":")) if body else ""
    headers = {
        "x-api-key-id":  cfg["api_key"],
        "authorization": f"Bearer {cfg['api_secret']}",
        "Content-Type":  "application/json",
        "Accept":        "application/json",
    }
    url = f"{API_BASE}{path}"
    req = urllib.request.Request(
        url,
        method=method,
        headers=headers,
        data=body_str.encode("utf-8") if body_str else None,
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        body_txt = e.read().decode("utf-8", errors="ignore")
        log(f"HTTP {e.code} on {method} {path}: {body_txt[:500]}")
        raise
    except urllib.error.URLError as e:
        log(f"Network error on {method} {path}: {e}")
        raise


# ---- Endpoints --------------------------------------------------------------
def list_accounts(cfg: dict) -> list:
    """GET /api/v0.1/accounts/list -> returns the user's brokerage accounts."""
    resp = api_request(cfg, "GET", "/api/v0.1/accounts/list")
    if isinstance(resp, dict):
        for k in ("accounts", "data", "items"):
            if isinstance(resp.get(k), list):
                return resp[k]
        # If the response is a dict but not wrapped, see if it itself looks like a list of accts
        return [resp] if "account_uuid" in resp else []
    return resp if isinstance(resp, list) else []


def get_symphony_stats(cfg: dict, account_uuid: str) -> dict | None:
    """
    GET /api/v0.1/portfolio/accounts/{account-id}/symphony-stats-meta
    "Get aggregate stats per symphony" — confirmed in api.composer.trade/docs.
    Returns {"symphonies": [{id, position_id, holdings: [...], value, ...}]}.
    Each holding is {ticker, price, allocation, amount, value,
    last_percent_change}. We use this for per-symphony allocation/value, then
    filter to the target symphony_id client-side.
    Returns None if the request fails for any reason (we'll fall back).
    """
    p = f"/api/v0.1/portfolio/accounts/{account_uuid}/symphony-stats-meta"
    try:
        log(f"GET {p}")
        resp = api_request(cfg, "GET", p)
        if isinstance(resp, list):
            resp = {"symphonies": resp}
        if isinstance(resp, dict):
            resp["_path"] = p
            return resp
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            raise
        log(f"  (symphony-stats-meta failed: HTTP {exc.code})")
    except Exception as exc:  # pylint: disable=broad-except
        log(f"  (symphony-stats-meta failed: {type(exc).__name__}: {exc})")
    return None


def get_account_holdings(cfg: dict, account_uuid: str) -> dict:
    """
    GET /api/v0.1/accounts/{uuid}/holdings -- confirmed working.
    Returns a top-level JSON LIST of positions across the whole account,
    each shaped like {"ticker": "...", "quantity": ..., "asset_class": "..."}.
    Normalized into {"holdings": [...]}.
    """
    p = f"/api/v0.1/accounts/{account_uuid}/holdings"
    log(f"GET {p}")
    resp = api_request(cfg, "GET", p)
    if isinstance(resp, list):
        resp = {"holdings": resp}
    if not isinstance(resp, dict):
        raise RuntimeError(f"Unexpected response type {type(resp).__name__}")
    resp["_path"] = p
    return resp


# ---- Yahoo Finance price enrichment ----------------------------------------
def fetch_yahoo_price(ticker: str) -> float | None:
    """
    Fetch the latest market price for a ticker from Yahoo Finance.
    Free, no auth required. Returns None on failure (logged).
    """
    url = (
        "https://query1.finance.yahoo.com/v8/finance/chart/"
        f"{urllib.parse.quote(ticker)}?range=1d&interval=1d"
    )
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 (composer-allocation-puller)"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
        result = data.get("chart", {}).get("result")
        if not result:
            return None
        meta = result[0].get("meta", {})
        price = meta.get("regularMarketPrice") or meta.get("previousClose")
        return float(price) if price is not None else None
    except Exception as exc:  # pylint: disable=broad-except
        log(f"  (price lookup failed for {ticker}: {type(exc).__name__}: {exc})")
        return None


def enrich_with_prices(positions: list[dict]) -> None:
    """In-place: add 'market_value' and 'weight_pct' using Yahoo prices."""
    log(f"Fetching prices for {len(positions)} tickers from Yahoo Finance...")
    total_value = 0.0
    for p in positions:
        if not p.get("ticker") or p.get("market_value"):
            continue
        price = fetch_yahoo_price(p["ticker"])
        qty = p.get("shares")
        if price is not None and isinstance(qty, (int, float)):
            mv = round(price * qty, 2)
            p["market_value"] = mv
            total_value += mv
    log(f"Total computed market value: ${total_value:,.2f}")
    if total_value > 0:
        for p in positions:
            mv = p.get("market_value")
            if isinstance(mv, (int, float)):
                p["weight_pct"] = round(100.0 * mv / total_value, 4)


# ---- Parsing ----------------------------------------------------------------
def _normalize_weight(weight) -> float | None:
    """Convert a 0-1 fraction or 0-100 percentage to a percentage value."""
    if not isinstance(weight, (int, float)):
        return weight
    return round(weight * 100, 4) if weight <= 1.0 else round(weight, 4)


def _row_from_item(item: dict) -> dict:
    """Pull a (ticker, weight, shares, market_value) row from a position-like dict."""
    ticker = (
        item.get("ticker")
        or item.get("symbol")
        or item.get("asset")
    )
    weight = (
        item.get("weight")
        or item.get("allocation")
        or item.get("percent")
        or item.get("target_weight")
        or item.get("allocation_percent")
        or item.get("pct")
    )
    return {
        "ticker":       ticker,
        "weight_pct":   _normalize_weight(weight),
        "shares": (
            item.get("quantity")
            or item.get("shares")
            or item.get("amount")  # symphony-stats-meta holdings use "amount"
        ),
        "market_value": (
            item.get("market_value")
            or item.get("value")
            or item.get("notional")
            or item.get("notional_value")
        ),
    }


def extract_positions_from_symphony_stats(
    stats_payload: dict, target_symphony_id: str
) -> list[dict]:
    """
    Pull positions for the specific symphony out of a symphony-stats-meta
    response. Per docs, the shape is:
        { "symphonies": [
            { "id": "<symphony_id>",
              "holdings": [
                  {"ticker": "...", "price": ..., "allocation": ...,
                   "amount": ..., "value": ..., "last_percent_change": ...}
              ],
              "value": ..., "name": ..., ...  } ] }
    We match the target by `id` and return its holdings.
    """
    # Find the list of symphonies in the payload
    sym_list = None
    for key in ("symphonies", "items", "data"):
        v = stats_payload.get(key)
        if isinstance(v, list):
            sym_list = v
            break
    if sym_list is None and isinstance(stats_payload, list):
        sym_list = stats_payload
    if sym_list is None:
        return []

    # Find the target symphony entry
    target = None
    for s in sym_list:
        if not isinstance(s, dict):
            continue
        sid = s.get("symphony_id") or s.get("id") or s.get("symphony")
        if str(sid) == str(target_symphony_id):
            target = s
            break

    if target is None:
        return []

    # Find the list of holdings within that symphony entry
    holdings = None
    for key in ("holdings", "positions", "allocations", "assets"):
        v = target.get(key)
        if isinstance(v, list):
            holdings = v
            break
    if holdings is None:
        holdings = []

    rows = [_row_from_item(it) for it in holdings if isinstance(it, dict)]

    # Include the symphony's idle cash as a $USD pseudo-position so the pie /
    # weight totals always sum to 100%. Composer's symphony-stats-meta returns
    # `cash` (a dollar amount) and `value` (total symphony value) at the
    # symphony level, separate from `holdings`. If there's pending cash that
    # hasn't been deployed yet, it shows up here.
    cash = target.get("cash")
    total_value = target.get("value")
    if isinstance(cash, (int, float)) and cash > 0:
        weight_pct = None
        if isinstance(total_value, (int, float)) and total_value > 0:
            weight_pct = round(100.0 * cash / total_value, 4)
        rows.append({
            "ticker":       "$USD",
            "weight_pct":   weight_pct,
            "shares":       round(cash, 2),  # 1 unit = $1
            "market_value": round(cash, 2),
        })

    return rows


def find_symphony_entry(stats_payload: dict, target_symphony_id: str) -> dict | None:
    """Return the raw symphony entry (full dict) for the target id, or None."""
    sym_list = None
    for key in ("symphonies", "items", "data"):
        v = stats_payload.get(key)
        if isinstance(v, list):
            sym_list = v
            break
    if sym_list is None and isinstance(stats_payload, list):
        sym_list = stats_payload
    if sym_list is None:
        return None
    for s in sym_list:
        if not isinstance(s, dict):
            continue
        sid = s.get("symphony_id") or s.get("id") or s.get("symphony")
        if str(sid) == str(target_symphony_id):
            return s
    return None


def extract_positions_from_account_holdings(payload: dict) -> list[dict]:
    """Extract positions from the whole-account /holdings response."""
    items = payload.get("holdings") or payload.get("data") or []
    if not isinstance(items, list):
        return []
    return [_row_from_item(it) for it in items if isinstance(it, dict)]


# ---- Dashboard generator ---------------------------------------------------
DASHBOARD_TEMPLATE_PATH = SCRIPT_DIR / "dashboard_template.html"


def _safe_float(s) -> float:
    try:
        return float(s) if s not in (None, "") else 0.0
    except (TypeError, ValueError):
        return 0.0


PASSWORD_OVERLAY_TEMPLATE = """
<div id="blee-pw-overlay" style="position:fixed;top:0;left:0;width:100%;height:100%;background:#0b1120;z-index:9999;display:flex;align-items:center;justify-content:center;">
  <div style="background:#1e293b;padding:40px;border-radius:16px;text-align:center;max-width:360px;width:90%;box-shadow:0 8px 32px rgba(0,0,0,0.5);">
    <div style="font-size:22px;font-weight:800;color:#fff;margin-bottom:6px;">&#128274; BLEE Quant Analytics</div>
    <div style="color:rgba(255,255,255,0.55);font-size:13px;margin-bottom:24px;">Daily Signal &mdash; Subscribers Only</div>
    <input id="blee-pw-input" type="password" placeholder="Enter password" style="width:100%;padding:12px 16px;border-radius:8px;border:1px solid rgba(255,255,255,0.15);background:rgba(255,255,255,0.07);color:#fff;font-size:15px;margin-bottom:12px;outline:none;box-sizing:border-box;">
    <button onclick="bleePwCheck()" style="width:100%;padding:12px;background:#f59e0b;color:#000;font-weight:700;font-size:15px;border:none;border-radius:8px;cursor:pointer;">Access Daily Signal</button>
    <div id="blee-pw-error" style="color:#ef4444;font-size:13px;margin-top:10px;display:none;">Incorrect password. Please try again.</div>
  </div>
</div>
<script>
(function() {
  var PW = '__BLEE_PASSWORD__';
  function bleePwCheck() {
    if (document.getElementById('blee-pw-input').value === PW) {
      document.getElementById('blee-pw-overlay').style.display = 'none';
      sessionStorage.setItem('blee_auth', '1');
    } else {
      document.getElementById('blee-pw-error').style.display = 'block';
    }
  }
  window.bleePwCheck = bleePwCheck;
  document.addEventListener('DOMContentLoaded', function() {
    var inp = document.getElementById('blee-pw-input');
    if (inp) inp.addEventListener('keypress', function(e) { if (e.key === 'Enter') bleePwCheck(); });
    if (sessionStorage.getItem('blee_auth') === '1') {
      document.getElementById('blee-pw-overlay').style.display = 'none';
    }
  });
})();
</script>
"""


def generate_dashboard(
    csv_path: Path,
    html_path: Path,
    symphony_id: str,
    symphony_name: str,
    account_uuid: str | None,
    password: str | None = None,
) -> None:
    """
    Read `csv_path` (this symphony's history) and write `html_path` with the
    BLEE Stock Analysis dashboard for that symphony.
    """
    if not csv_path.exists():
        log(f"(no CSV yet at {csv_path.name}, skipping dashboard generation)")
        return
    if not DASHBOARD_TEMPLATE_PATH.exists():
        log(f"(dashboard template missing at {DASHBOARD_TEMPLATE_PATH.name}, skipping)")
        return

    # Strip NUL bytes that Windows sometimes embeds in CSV files
    import io as _io
    raw_bytes = csv_path.read_bytes().replace(b"\x00", b"")
    rows = list(csv.DictReader(_io.StringIO(raw_bytes.decode("utf-8"))))
    if not rows:
        log("(empty CSV, skipping dashboard generation)")
        return

    # Group by date, deduping (date, ticker) — keep the last row per ticker
    # within each date so duplicate runs never double-count.
    by_date_map: dict[str, dict[str, dict]] = {}
    for r in rows:
        d = r.get("date") or ""
        t = r.get("ticker") or ""
        if d and t:
            by_date_map.setdefault(d, {})[t] = r
    by_date: dict[str, list[dict]] = {
        d: list(tmap.values()) for d, tmap in by_date_map.items()
    }
    if not by_date:
        log("(no dated rows, skipping dashboard generation)")
        return
    dates_sorted = sorted(by_date.keys())

    # Daily portfolio totals
    value_history = []
    for d in dates_sorted:
        total = sum(_safe_float(r.get("market_value")) for r in by_date[d])
        value_history.append({"date": d, "total": round(total, 2)})

    # Today's allocation, sorted by market value desc
    today = dates_sorted[-1]
    today_alloc = sorted(
        [
            {
                "ticker":       r.get("ticker", ""),
                "weight_pct":   _safe_float(r.get("weight_pct")),
                "shares":       _safe_float(r.get("shares")),
                "market_value": _safe_float(r.get("market_value")),
            }
            for r in by_date[today] if r.get("ticker")
        ],
        key=lambda x: -x["market_value"],
    )

    total_value      = value_history[-1]["total"]
    total_return_pct: float | None = None
    annualized_pct:   float | None = None
    day_change_pct:   float | None = None

    if len(value_history) >= 2:
        first = value_history[0]["total"]
        last  = value_history[-1]["total"]
        prev  = value_history[-2]["total"]
        if first > 0:
            total_return_pct = round((last / first - 1) * 100, 4)
        if prev > 0:
            day_change_pct = round((last / prev - 1) * 100, 4)
        try:
            d0 = dt.date.fromisoformat(value_history[0]["date"])
            d1 = dt.date.fromisoformat(value_history[-1]["date"])
            days = (d1 - d0).days
            if days >= 14 and first > 0:
                annualized_pct = round(((last / first) ** (365.0 / days) - 1) * 100, 4)
        except (ValueError, ZeroDivisionError):
            pass

    # Tickers history for stacked area
    all_tickers = sorted({r.get("ticker") for r in rows if r.get("ticker")})
    weight_history: dict[str, list[float]] = {t: [] for t in all_tickers}
    for d in dates_sorted:
        ticker_to_w = {
            r.get("ticker"): _safe_float(r.get("weight_pct"))
            for r in by_date[d]
        }
        for t in all_tickers:
            weight_history[t].append(ticker_to_w.get(t, 0.0))

    run_datetime = dt.datetime.now().strftime("%m/%d/%Y %I:%M %p")
    data = {
        "symphony_id":           symphony_id,
        "symphony_name":         symphony_name or "",
        "csv_filename":          csv_path.name,
        "account_uuid":          account_uuid or "",
        "last_updated":          today,
        "run_datetime":          run_datetime,
        "total_value":           total_value,
        "day_change_pct":        day_change_pct,
        "total_return_pct":      total_return_pct,
        "annualized_return_pct": annualized_pct,
        "today_allocations":     today_alloc,
        "value_history":         value_history,
        "all_tickers":           all_tickers,
        "weight_history":        weight_history,
        "dates":                 dates_sorted,
    }

    template = DASHBOARD_TEMPLATE_PATH.read_text(encoding="utf-8")
    html = template.replace("/* __DATA_JSON__ */ {}", json.dumps(data))
    if password:
        overlay = PASSWORD_OVERLAY_TEMPLATE.replace("__BLEE_PASSWORD__", password)
        html = html.replace("<body>", "<body>" + overlay, 1)
        log(f"  Password protection injected into {html_path.name}")
    html_path.write_text(html, encoding="utf-8")
    log(f"Generated dashboard -> {html_path.name} "
        f"(value=${total_value:,.2f}, days={len(dates_sorted)})")


# ---- CSV write (idempotent) ------------------------------------------------
CSV_HEADER = ["date", "symphony_id", "ticker",
              "weight_pct", "shares", "market_value", "source"]


def write_symphony_csv(
    csv_path: Path, today: str, symphony_id: str,
    positions: list[dict], source_used: str,
) -> None:
    """
    Idempotent write: drop any existing rows for today's date, then rewrite
    the whole file with prior-day rows + today's fresh rows. Safe to call
    multiple times per day; self-heals duplicates.
    """
    existing_rows: list[list[str]] = []
    if csv_path.exists():
        with open(csv_path, newline="") as f:
            reader = csv.reader(f)
            try:
                next(reader)  # skip header
            except StopIteration:
                pass
            for row in reader:
                if not row:
                    continue
                if row[0] != today:  # row[0] is date
                    existing_rows.append(row)

    with open(csv_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(CSV_HEADER)
        for row in existing_rows:
            writer.writerow(row)
        for p in positions:
            writer.writerow([
                today, symphony_id,
                p["ticker"], p["weight_pct"],
                p["shares"], p["market_value"], source_used,
            ])
    log(f"  Wrote {len(positions)} rows for {today} to {csv_path.name} "
        f"(kept {len(existing_rows)} prior rows, source={source_used})")


# ---- Main -------------------------------------------------------------------
def main() -> int:
    log("=== Composer daily allocation pull ===")
    cfg = load_config()
    symphonies = _resolve_symphonies(cfg)
    if not symphonies:
        log("ERROR: no symphonies configured")
        return 1
    log(f"Configured symphonies: {[s['id'] for s in symphonies]}")

    account_uuid = cfg.get("account_uuid")
    if not account_uuid:
        log("No account_uuid in config; discovering via /accounts/list...")
        accts = list_accounts(cfg)
        if not accts:
            log("ERROR: no accounts returned from API")
            return 1
        account_uuid = (
            accts[0].get("account_uuid")
            or accts[0].get("uuid")
            or accts[0].get("id")
        )
        log(f"Using first account: {account_uuid}")
        log("(Tip: copy this account_uuid into composer_config.json to skip the lookup next run.)")

    today = dt.date.today().isoformat()

    # Fetch symphony-stats-meta ONCE; share across all configured symphonies.
    log("Fetching per-symphony stats from /portfolio/.../symphony-stats-meta...")
    stats_payload = get_symphony_stats(cfg, account_uuid)
    if stats_payload is not None:
        stats_path = SCRIPT_DIR / f"composer_symphony_stats_{today}.json"
        with open(stats_path, "w") as f:
            json.dump(stats_payload, f, indent=2, default=str)
        log(f"Saved symphony-stats response to {stats_path.name}")

    # For each configured symphony, extract its slice and write outputs.
    for sym in symphonies:
        sid       = sym["id"]
        sname     = sym["name"]
        csv_path  = SCRIPT_DIR / sym["csv"]
        html_path = SCRIPT_DIR / sym["html"]
        password  = sym.get("password") or None
        log(f"--- {sname or sid} ({sid}) ---")

        positions: list[dict] = []
        source_used = ""

        if stats_payload is not None:
            positions = extract_positions_from_symphony_stats(stats_payload, sid)
            if positions:
                source_used = "symphony-stats-meta"
                log(f"  Got {len(positions)} positions from {source_used}")
            else:
                log(f"  WARN: symphony-stats-meta returned no positions for {sid} "
                    f"(check {today} JSON to verify the id matches one in the response)")

        # Fallback only makes sense if there's a single configured symphony,
        # since /holdings can't tell us which symphony a position belongs to.
        if not positions and len(symphonies) == 1:
            log("  Falling back to /holdings + Yahoo prices (whole-account view)")
            holdings_payload = get_account_holdings(cfg, account_uuid)
            raw_path = SCRIPT_DIR / f"composer_raw_{today}.json"
            with open(raw_path, "w") as f:
                json.dump(holdings_payload, f, indent=2, default=str)
            positions = extract_positions_from_account_holdings(holdings_payload)
            source_used = "account-holdings+yahoo-prices"
            needs_prices = any(
                p.get("ticker") and not isinstance(p.get("market_value"), (int, float))
                for p in positions
            )
            if needs_prices:
                enrich_with_prices(positions)

        if not positions:
            log(f"  ERROR: no positions found for {sid}; skipping CSV/HTML for this symphony")
            continue

        # Save a per-symphony JSON snapshot of today's slice (handy for
        # debugging). Includes the raw symphony entry from the API so you can
        # inspect cash, value, and any other fields Composer returned.
        raw_entry = (
            find_symphony_entry(stats_payload, sid)
            if stats_payload is not None else None
        )
        slice_path = SCRIPT_DIR / f"{csv_path.stem}_{today}.json"
        with open(slice_path, "w") as f:
            json.dump({
                "date":            today,
                "symphony_id":     sid,
                "symphony_name":   sname,
                "source":          source_used,
                "positions":       positions,
                "raw_api_entry":   raw_entry,
            }, f, indent=2, default=str)
        log(f"  Saved today's slice to {slice_path.name}")

        # Write to per-symphony CSV (idempotent).
        write_symphony_csv(csv_path, today, sid, positions, source_used)

        # Regenerate this symphony's dashboard.
        try:
            generate_dashboard(csv_path, html_path, sid, sname, account_uuid, password)
        except Exception as e:  # pylint: disable=broad-except
            log(f"  (dashboard generation failed: {type(e).__name__}: {e})")

    log("=== Done ===")

    # ---- Stamp last-updated timestamp into static HTML pages -----------------
    import re as _re
    now_str = dt.datetime.now().strftime("%m/%d/%Y %I:%M %p")
    stamp_pages = ["index.html", "performance1.html"]
    for page in stamp_pages:
        page_path = SCRIPT_DIR / page
        if not page_path.exists():
            continue
        try:
            content = page_path.read_text(encoding="utf-8")
            updated = _re.sub(
                r'<span id="blee-updated">[^<]*</span>',
                f'<span id="blee-updated">{now_str}</span>',
                content
            )
            if updated != content:
                page_path.write_text(updated, encoding="utf-8")
                log(f"Stamped last-updated ({now_str}) into {page}")
        except Exception as e:
            log(f"  (could not stamp timestamp into {page}: {e})")

    # ---- Push updated files to GitHub ----------------------------------------
    log("--- Pushing updates to GitHub ---")
    try:
        import os
        git_dir = str(SCRIPT_DIR)
        def git(cmd: str) -> int:
            full = f'git -C "{git_dir}" {cmd}'
            log(f"  $ {full}")
            rc = os.system(full)
            if rc != 0:
                log(f"  WARNING: command exited with code {rc}")
            return rc

        git("add .")
        git(f'commit -m "daily auto update {today}"')
        rc = git("push")
        if rc == 0:
            log("GitHub push successful.")
        else:
            log("GitHub push failed — check remote/auth settings.")
    except Exception as e:  # pylint: disable=broad-except
        log(f"  (GitHub push failed: {type(e).__name__}: {e})")

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as e:  # pylint: disable=broad-except
        log(f"FATAL: {type(e).__name__}: {e}")
        sys.exit(1)
