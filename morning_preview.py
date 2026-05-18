#!/usr/bin/env python3
"""
morning_preview.py — BLEE Quant Analytics
==========================================
Runs at 10:00 AM ET daily (Windows Task Scheduler). Calls the Composer API
to get the current symphony allocation (live market data), compares against
yesterday's saved allocation, and publishes results to GitHub.

Reads:  composer_config.json  (same API credentials as composer_pull_allocation.py)
Writes: morning_preview.html  (standalone preview page)
        index2.html           (injects Morning Preview section between marker comments)

Schedule: Windows Task Scheduler — Mon–Fri 10:00 AM ET
"""

from __future__ import annotations

import datetime as dt
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

# ── Paths ─────────────────────────────────────────────────────────────────────
SCRIPT_DIR   = Path(__file__).resolve().parent
CONFIG_PATH  = SCRIPT_DIR / "composer_config.json"
LOG_PATH     = SCRIPT_DIR / "morning_preview.log"
OUTPUT_HTML  = SCRIPT_DIR / "morning_preview.html"
INDEX2_HTML  = SCRIPT_DIR / "index2.html"

API_BASE = "https://api.composer.trade"

# Symphony to preview (BLEE-187)
TARGET_SYMPHONY_ID = "qjmHJ3IR19kmaAlbgkNj"


# ── Logging ───────────────────────────────────────────────────────────────────
def log(msg: str) -> None:
    ts = dt.datetime.now().isoformat(timespec="seconds")
    line = f"[{ts}] {msg}"
    print(line)
    with open(LOG_PATH, "a") as f:
        f.write(line + "\n")


# ── Config ────────────────────────────────────────────────────────────────────
def load_config() -> dict:
    with open(CONFIG_PATH) as f:
        return json.load(f)


# ── API ───────────────────────────────────────────────────────────────────────
def api_request(cfg: dict, path: str) -> dict:
    headers = {
        "x-api-key-id":  cfg["api_key"],
        "authorization": f"Bearer {cfg['api_secret']}",
        "Accept":        "application/json",
    }
    req = urllib.request.Request(f"{API_BASE}{path}", headers=headers)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def list_accounts(cfg: dict) -> list:
    resp = api_request(cfg, "/api/v0.1/accounts/list")
    if isinstance(resp, list):
        return resp
    for k in ("accounts", "data", "items"):
        if isinstance(resp.get(k), list):
            return resp[k]
    return []


def get_symphony_stats(cfg: dict, account_uuid: str) -> dict | None:
    p = f"/api/v0.1/portfolio/accounts/{account_uuid}/symphony-stats-meta"
    try:
        return api_request(cfg, p)
    except Exception as e:
        log(f"  symphony-stats-meta failed: {e}")
        return None


def find_symphony(stats: dict, symphony_id: str) -> dict | None:
    for key in ("symphonies", "data", "items"):
        items = stats.get(key, [])
        if isinstance(items, list):
            for s in items:
                sid = s.get("symphony_id") or s.get("id") or s.get("symphony")
                if str(sid) == symphony_id:
                    return s
    return None


def extract_positions(symphony_entry: dict) -> list[dict]:
    holdings = []
    for key in ("holdings", "positions", "allocations", "assets"):
        v = symphony_entry.get(key)
        if isinstance(v, list):
            holdings = v
            break

    rows = []
    for item in holdings:
        if not isinstance(item, dict):
            continue
        ticker = item.get("ticker") or item.get("symbol") or ""
        if not ticker or ticker in ("$USD", "USD", "CASH"):
            continue
        weight = (item.get("weight_pct") or item.get("allocation") or
                  item.get("target_weight") or item.get("allocation_percent") or 0)
        try:
            weight = float(weight)
        except (TypeError, ValueError):
            weight = 0.0
        rows.append({"ticker": ticker, "weight_pct": round(weight, 2)})

    return sorted(rows, key=lambda x: x["weight_pct"], reverse=True)


# ── Load yesterday's allocation ────────────────────────────────────────────────
def load_yesterday_allocation() -> dict[str, float]:
    """
    Load the most recent saved allocation JSON for comparison.
    Returns {ticker: weight_pct}.
    """
    files = sorted(SCRIPT_DIR.glob("composer_allocations_185_*.json"), reverse=True)
    if not files:
        return {}
    with open(files[0]) as f:
        data = json.load(f)
    return {
        p["ticker"]: p.get("weight_pct", 0.0)
        for p in data.get("positions", [])
        if p.get("ticker") and p["ticker"] not in ("$USD", "USD", "CASH")
    }


# ── Compute delta ─────────────────────────────────────────────────────────────
def compute_changes(current: list[dict], previous: dict[str, float]) -> list[dict]:
    result = []
    seen = set()
    for pos in current:
        t = pos["ticker"]
        seen.add(t)
        prev_w = previous.get(t, 0.0)
        curr_w = pos["weight_pct"]
        delta  = round(curr_w - prev_w, 2)
        if curr_w == 0 and prev_w == 0:
            continue
        if prev_w == 0:
            action = "NEW"
        elif curr_w == 0:
            action = "EXIT"
        elif delta > 0.4:
            action = "BUY"
        elif delta < -0.4:
            action = "SELL"
        else:
            action = "HOLD"
        result.append({
            "ticker": t,
            "prev_pct": round(prev_w, 1),
            "curr_pct": round(curr_w, 1),
            "delta":    delta,
            "action":  action,
        })
    # Tickers that are in previous but no longer in current
    for t, prev_w in previous.items():
        if t not in seen and prev_w > 0:
            result.append({
                "ticker": t,
                "prev_pct": round(prev_w, 1),
                "curr_pct": 0.0,
                "delta":    round(-prev_w, 2),
                "action":  "EXIT",
            })
    return sorted(result, key=lambda x: x["curr_pct"], reverse=True)


# ── HTML generation ───────────────────────────────────────────────────────────
ACTION_STYLE = {
    "BUY":  ("🟢", "#10b981", "Buy"),
    "SELL": ("🔴", "#ef4444", "Sell"),
    "HOLD": ("⚪", "#9ca3af", "Hold"),
    "NEW":  ("🆕", "#f59e0b", "New Position"),
    "EXIT": ("🚪", "#6b7280", "Exit"),
}


def build_html(positions: list[dict], changes: list[dict], symphony_name: str,
               prev_date: str, as_of: str) -> str:

    rows_html = ""
    for c in changes:
        icon, color, label = ACTION_STYLE.get(c["action"], ("⚪", "#9ca3af", c["action"]))
        delta_str = f"+{c['delta']}%" if c["delta"] > 0 else f"{c['delta']}%"
        delta_color = "#10b981" if c["delta"] > 0 else ("#ef4444" if c["delta"] < 0 else "#9ca3af")
        rows_html += f"""
        <tr>
          <td><strong style="font-size:15px;">{c['ticker']}</strong></td>
          <td style="color:#9ca3af;">{c['prev_pct']}%</td>
          <td style="color:#fff;font-weight:700;">{c['curr_pct']}%</td>
          <td style="color:{delta_color};font-weight:700;">{delta_str}</td>
          <td><span style="color:{color};font-weight:700;">{icon} {label}</span></td>
        </tr>"""

    total_pct = sum(c["curr_pct"] for c in changes)

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>Tomorrow's Signal Preview — BLEE Quant Analytics</title>
<style>
  *{{box-sizing:border-box;margin:0;padding:0}}
  body{{font-family:-apple-system,system-ui,'Segoe UI',sans-serif;
       background:#0b1120;color:#fff;min-height:100vh;padding:0;}}

  /* ── Nav (matches site) ── */
  .nav{{background:#0b1120;border-bottom:1px solid #1f2937;
        padding:0 24px;display:flex;align-items:center;
        justify-content:space-between;height:60px;position:sticky;top:0;z-index:100;}}
  .logo{{font-size:18px;font-weight:800;color:#f5a623;text-decoration:none;}}
  .logo span{{color:#fff;}}
  .nav-links a{{color:#9ca3af;text-decoration:none;font-size:14px;font-weight:600;
                margin-left:20px;}}
  .nav-links a:hover{{color:#fff;}}
  .nav-links a.active{{color:#fff;}}

  /* ── Hero banner ── */
  .hero{{background:linear-gradient(135deg,#0b1a35 0%,#0d2240 100%);
         padding:40px 24px 32px;text-align:center;
         border-bottom:1px solid #1f2937;}}
  .hero-label{{font-size:11px;font-weight:700;color:#f5a623;letter-spacing:.12em;
               text-transform:uppercase;margin-bottom:10px;}}
  .hero h1{{font-size:28px;font-weight:800;margin-bottom:8px;}}
  .hero .sub{{color:#9ca3af;font-size:14px;}}
  .as-of{{display:inline-block;background:#1f2937;border:1px solid #374151;
           border-radius:8px;padding:6px 16px;font-size:12px;color:#d1d5db;
           margin-top:14px;}}

  /* ── Content ── */
  .content{{max-width:820px;margin:36px auto;padding:0 20px;}}

  /* ── Preview card ── */
  .card{{background:#111827;border:1px solid #1f2937;border-radius:14px;
         padding:28px;margin-bottom:24px;}}
  .card-title{{font-size:13px;font-weight:700;color:#9ca3af;letter-spacing:.08em;
               text-transform:uppercase;margin-bottom:16px;}}

  table{{width:100%;border-collapse:collapse;}}
  th{{font-size:11px;font-weight:700;color:#6b7280;letter-spacing:.08em;
      text-transform:uppercase;padding:8px 12px;border-bottom:1px solid #1f2937;
      text-align:left;}}
  td{{padding:12px 12px;border-bottom:1px solid #1f2937;font-size:14px;
      color:#d1d5db;}}
  tr:last-child td{{border:0;}}
  tr:hover td{{background:rgba(255,255,255,0.02);}}

  /* ── Legend ── */
  .legend{{display:flex;gap:20px;flex-wrap:wrap;margin-top:20px;font-size:12px;color:#6b7280;}}
  .legend span{{display:flex;align-items:center;gap:6px;}}

  /* ── Disclaimer ── */
  .disclaimer{{background:#0f1929;border:1px solid #1f2937;border-radius:10px;
               padding:16px 20px;font-size:12px;color:#6b7280;line-height:1.7;
               margin-top:24px;}}

  /* ── Footer ── */
  .footer{{text-align:center;color:#4b5563;font-size:12px;padding:32px 20px;}}
  .footer a{{color:#f5a623;text-decoration:none;}}

  .badge{{display:inline-block;font-size:10px;font-weight:700;letter-spacing:.06em;
          padding:3px 10px;border-radius:20px;text-transform:uppercase;}}
  .badge-preview{{background:rgba(245,166,35,0.15);color:#f5a623;border:1px solid #f5a62344;}}
</style>
</head>
<body>

<nav class="nav">
  <a class="logo" href="index.html">BLEE <span>Quant</span></a>
  <div class="nav-links">
    <a href="index.html">Home</a>
    <a href="mission.html">Our Mission</a>
    <a href="marketDailySummary.html">Market Forecast</a>
    <a href="index2.html">Daily Signal</a>
    <a href="Algorithm185History.html">Backtest</a>
    <a href="performance1.html">Performance</a>
    <a href="subscribe.html" style="color:#f5a623;">Subscribe</a>
  </div>
</nav>

<div class="hero">
  <div class="hero-label">📡 BLEE — Tomorrow's Reallocation Signal</div>
  <h1>Tomorrow's Predicted Portfolio Allocation</h1>
  <p class="sub">{symphony_name}</p>
  <div class="as-of">
    🕙 Captured: {as_of} ET &nbsp;·&nbsp; Based on today's live market data
    &nbsp;·&nbsp; <span class="badge badge-preview">Intraday Preview</span>
  </div>
</div>

<div class="content">

  <div class="card">
    <div class="card-title">📊 Predicted Reallocation — Tomorrow's Opening Position</div>
    <p style="font-size:13px;color:#6b7280;margin-bottom:16px;line-height:1.6;">
      Based on live market data at {as_of} ET, the algorithm signals the following
      reallocation. Trades execute at today's market close (~3:55 PM ET),
      resulting in this portfolio for <strong style="color:#fff;">tomorrow's market opening</strong>.
    </p>
    <table>
      <thead>
        <tr>
          <th>Ticker</th>
          <th>Current ({prev_date})</th>
          <th>Tomorrow's Target</th>
          <th>Change</th>
          <th>Signal</th>
        </tr>
      </thead>
      <tbody>
        {rows_html}
      </tbody>
    </table>
    <div class="legend">
      <span>🟢 BUY — Increase position</span>
      <span>🔴 SELL — Reduce position</span>
      <span>⚪ HOLD — No change (&lt;0.4%)</span>
      <span>🆕 NEW — Enter position</span>
      <span>🚪 EXIT — Close position</span>
    </div>
  </div>

  <div class="disclaimer">
    ⚠️ <strong>Intraday Preview — Subject to Change.</strong>
    This prediction is based on live market data as of {as_of} ET. Because market
    prices continue moving until close, the final reallocation signal (published ~3:55 PM ET)
    may differ. Use this as an early indication only — not as a trade instruction.
    This is not investment advice. Subscribers make their own trading decisions.
  </div>

  <div class="footer">
    <a href="index.html">← Back to Home</a> &nbsp;·&nbsp;
    <a href="index2.html">View Final Daily Signal →</a>
    <br><br>
    © {dt.date.today().year} BLEE Quant Analytics · Educational research only
  </div>

</div>

<!-- Firebase + user bar -->
<script src="https://www.gstatic.com/firebasejs/10.12.0/firebase-app-compat.js"></script>
<script src="https://www.gstatic.com/firebasejs/10.12.0/firebase-auth-compat.js"></script>
<script src="https://www.gstatic.com/firebasejs/10.12.0/firebase-firestore-compat.js"></script>
<script src="firebase-config.js"></script>
<script src="user_bar.js"></script>

</body>
</html>
"""


# ── Inject preview section into index2.html ───────────────────────────────────
def build_index2_section(changes: list[dict], symphony_name: str,
                          prev_date: str, as_of: str) -> str:
    rows = ""
    for c in changes:
        icon, color, label = ACTION_STYLE.get(c["action"], ("⚪", "#9ca3af", c["action"]))
        delta_str   = f"+{c['delta']}%" if c["delta"] > 0 else f"{c['delta']}%"
        delta_color = "#10b981" if c["delta"] > 0 else ("#ef4444" if c["delta"] < 0 else "#9ca3af")
        rows += (
            f'<tr>'
            f'<td><strong>{c["ticker"]}</strong></td>'
            f'<td style="color:#9ca3af">{c["prev_pct"]}%</td>'
            f'<td style="font-weight:700">{c["curr_pct"]}%</td>'
            f'<td style="color:{delta_color};font-weight:700">{delta_str}</td>'
            f'<td style="color:{color};font-weight:700">{icon} {label}</td>'
            f'</tr>'
        )

    return f"""  <!-- MORNING_PREVIEW_START -->
  <section class="card" id="morning-preview-section" style="margin-bottom:16px;background:linear-gradient(135deg,#0b1a35,#0d2240);border:1px solid rgba(245,166,35,0.25);">
    <div style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:8px;margin-bottom:14px;">
      <h2 style="margin:0;">📡 Tomorrow's Predicted Reallocation</h2>
      <span style="font-size:11px;color:#f5a623;font-weight:700;background:rgba(245,166,35,0.12);border:1px solid rgba(245,166,35,0.3);padding:4px 12px;border-radius:20px;">
        🕙 Captured {as_of} ET &nbsp;·&nbsp; Intraday Preview
      </span>
    </div>
    <p style="font-size:12px;color:#6b7280;margin-bottom:12px;line-height:1.6;">
      Based on live market data at {as_of} ET. Trades execute at today's close (~3:55 PM ET),
      setting up this allocation for <strong style="color:#d1d5db;">tomorrow's market opening</strong>.
      Final signal may shift before close.
    </p>
    <div style="overflow-x:auto;">
      <table style="width:100%;border-collapse:collapse;font-size:13px;">
        <thead>
          <tr style="border-bottom:1px solid #1f2937;">
            <th style="padding:8px 10px;text-align:left;color:#6b7280;font-size:11px;text-transform:uppercase;letter-spacing:.06em;">Ticker</th>
            <th style="padding:8px 10px;text-align:left;color:#6b7280;font-size:11px;text-transform:uppercase;letter-spacing:.06em;">Current ({prev_date})</th>
            <th style="padding:8px 10px;text-align:left;color:#6b7280;font-size:11px;text-transform:uppercase;letter-spacing:.06em;">Tomorrow's Target</th>
            <th style="padding:8px 10px;text-align:left;color:#6b7280;font-size:11px;text-transform:uppercase;letter-spacing:.06em;">Change</th>
            <th style="padding:8px 10px;text-align:left;color:#6b7280;font-size:11px;text-transform:uppercase;letter-spacing:.06em;">Signal</th>
          </tr>
        </thead>
        <tbody style="color:#d1d5db;">
          {rows}
        </tbody>
      </table>
    </div>
    <p style="font-size:12px;color:#4b5563;margin-top:12px;line-height:1.6;">
      ⚠️ Intraday preview — subject to change before market close.
      &nbsp;<a href="morning_preview.html" style="color:#f5a623;text-decoration:none;">View full preview page →</a>
    </p>
  </section>
  <!-- MORNING_PREVIEW_END -->"""


def inject_into_index2(section_html: str) -> bool:
    """Replace content between MORNING_PREVIEW_START and MORNING_PREVIEW_END in index2.html."""
    if not INDEX2_HTML.exists():
        log(f"  index2.html not found at {INDEX2_HTML}")
        return False

    content = INDEX2_HTML.read_text(encoding="utf-8")
    start_marker = "<!-- MORNING_PREVIEW_START -->"
    end_marker   = "<!-- MORNING_PREVIEW_END -->"

    start_idx = content.find(start_marker)
    end_idx   = content.find(end_marker)

    if start_idx == -1 or end_idx == -1:
        log("  WARNING: MORNING_PREVIEW markers not found in index2.html — skipping inject")
        return False

    new_content = content[:start_idx] + section_html + "\n" + content[end_idx + len(end_marker):]
    INDEX2_HTML.write_text(new_content, encoding="utf-8")
    log(f"✅ Injected morning preview into index2.html")
    return True


# ── Git push ───────────────────────────────────────────────────────────────────
def git_push(as_of: str) -> None:
    try:
        # Remove stale lock file if present
        lock = SCRIPT_DIR / ".git" / "index.lock"
        if lock.exists():
            lock.unlink(missing_ok=True)

        subprocess.run(
            ["git", "add", "morning_preview.html", "index2.html"],
            cwd=SCRIPT_DIR, check=True, capture_output=True
        )
        subprocess.run(
            ["git", "commit", "-m", f"Auto: Morning Preview {as_of}"],
            cwd=SCRIPT_DIR, check=True, capture_output=True
        )
        subprocess.run(
            ["git", "push", "origin", "main"],
            cwd=SCRIPT_DIR, check=True, capture_output=True
        )
        log("✅ Pushed morning_preview.html + index2.html to GitHub Pages")
    except subprocess.CalledProcessError as e:
        log(f"⚠️  Git push failed: {e.stderr.decode()[:300] if e.stderr else e}")


# ── Main ──────────────────────────────────────────────────────────────────────
def main() -> None:
    log("=" * 60)
    log("Morning Preview — starting")

    cfg = load_config()

    # Discover account UUID
    account_uuid = cfg.get("account_uuid") or ""
    if not account_uuid:
        log("Discovering account UUID...")
        accounts = list_accounts(cfg)
        if accounts:
            for acc in accounts:
                uuid = acc.get("id") or acc.get("uuid") or acc.get("account_uuid") or ""
                if uuid:
                    account_uuid = uuid
                    log(f"  Found account: {account_uuid}")
                    break
        if not account_uuid:
            log("ERROR: Could not find account UUID. Check composer_config.json.")
            sys.exit(1)

    # Get current allocation from API
    log("Fetching current symphony allocation from Composer API...")
    stats = get_symphony_stats(cfg, account_uuid)
    if not stats:
        log("ERROR: Could not fetch symphony stats.")
        sys.exit(1)

    symphony_entry = find_symphony(stats, TARGET_SYMPHONY_ID)
    if not symphony_entry:
        log(f"ERROR: Symphony {TARGET_SYMPHONY_ID} not found in account stats.")
        sys.exit(1)

    symphony_name = symphony_entry.get("name", "BLEE-187")
    current_positions = extract_positions(symphony_entry)
    log(f"  Got {len(current_positions)} positions from API")
    for p in current_positions:
        log(f"    {p['ticker']:8s}  {p['weight_pct']:6.2f}%")

    # Load previous allocation for comparison
    log("Loading previous allocation for comparison...")
    previous = load_yesterday_allocation()
    prev_files = sorted(SCRIPT_DIR.glob("composer_allocations_185_*.json"), reverse=True)
    prev_date = prev_files[0].stem.replace("composer_allocations_185_", "") if prev_files else "N/A"
    log(f"  Previous date: {prev_date}")

    # Compute changes
    changes = compute_changes(current_positions, previous)
    log("  Changes:")
    for c in changes:
        log(f"    {c['ticker']:8s}  {c['prev_pct']:5.1f}% → {c['curr_pct']:5.1f}%  ({c['action']})")

    # Build & write standalone morning_preview.html
    now_str  = dt.datetime.now().strftime("%Y-%m-%d %I:%M %p")
    html     = build_html(current_positions, changes, symphony_name, prev_date, now_str)
    OUTPUT_HTML.write_text(html, encoding="utf-8")
    log(f"✅ Written: {OUTPUT_HTML}")

    # Inject preview section into index2.html
    section = build_index2_section(changes, symphony_name, prev_date, now_str)
    inject_into_index2(section)

    # Push both files to GitHub
    git_push(now_str)
    log("Morning Preview complete.")
    log("=" * 60)


if __name__ == "__main__":
    main()
