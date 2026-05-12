#!/usr/bin/env python3
"""
archive_pages.py — BLEE Daily Archive

Run BEFORE composer_pull_allocation.py and market_report.py overwrite the
live pages. This script:
  1. Copies marketDailySummary.html → BackLog/marketForecast_YYYY-MM-DD.html
  2. Copies index2.html             → BackLog/dailySignal_YYYY-MM-DD.html
  3. Patches each archived copy:
       • Unifies sessionStorage key to 'blee_auth' (one login, all pages)
       • Adds a purple archive banner with date + "Back to Archive Index" link
       • Fixes all relative hrefs to work from inside BackLog/ subfolder
  4. Prunes archive files older than 365 days
  5. Rebuilds BackLog/index.html (master list, newest first)

Usage (called automatically by run.bat):
    python archive_pages.py
"""

from __future__ import annotations

import datetime as dt
import re
import shutil
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────────────

SCRIPT_DIR  = Path(__file__).resolve().parent
BACKLOG_DIR = SCRIPT_DIR / "BackLog"
LOG_PATH    = SCRIPT_DIR / "composer_run.log"

PASSWORD    = "Blee@daily2026"
SESSION_KEY = "blee_auth"          # single key shared by all protected pages
KEEP_DAYS   = 365

PAGES = [
    {
        "src":    SCRIPT_DIR / "marketDailySummary.html",
        "prefix": "marketForecast",
        "label":  "Market Weather Forecast",
        "icon":   "🌤️",
    },
    {
        "src":    SCRIPT_DIR / "index2.html",
        "prefix": "dailySignal",
        "label":  "Daily Signal",
        "icon":   "📊",
    },
]


# ── Logging ───────────────────────────────────────────────────────────────────

def log(msg: str) -> None:
    ts   = dt.datetime.now().isoformat(timespec="seconds")
    line = f"[{ts}] archive: {msg}"
    print(line)
    with open(LOG_PATH, "a") as f:
        f.write(line + "\n")


# ── HTML patching ─────────────────────────────────────────────────────────────

def patch_archive(html: str, label: str, date_str: str) -> str:
    """
    Transform a live page into an archived copy stored in BackLog/.

    Changes made:
      1. Unify all sessionStorage keys → SESSION_KEY
      2. Update password variable to current PASSWORD
      3. Fix relative hrefs so links work from BackLog/ (prepend ../)
      4. Insert purple archive banner after the closing </nav> tag
    """

    # 1. Unify sessionStorage keys
    html = re.sub(
        r"(sessionStorage\.(?:setItem|getItem|removeItem)\()'blee_auth[^']*'",
        rf"\1'{SESSION_KEY}'",
        html,
    )

    # 2. Ensure password variable is current
    html = re.sub(r"var PW = '[^']*';", f"var PW = '{PASSWORD}';", html)

    # 3. Fix relative hrefs: href="foo.html" → href="../foo.html"
    #    Skip hrefs that already start with http, #, or ../
    def fix_href(m: re.Match) -> str:
        href = m.group(1)
        if href.startswith(("http", "#", "../", "BackLog/")):
            return m.group(0)
        return f'href="../{href}"'

    html = re.sub(r'href="([^"]+)"', fix_href, html)

    # 4. Insert archive banner after the first </nav>
    try:
        pretty_date = dt.date.fromisoformat(date_str).strftime("%B %d, %Y")
    except ValueError:
        pretty_date = date_str

    banner = (
        f'\n<div style="background:#7c3aed;color:#fff;text-align:center;'
        f'padding:9px 16px;font-size:13px;font-weight:600;letter-spacing:0.02em;">'
        f'📅 Archive &mdash; {label} &mdash; {pretty_date}'
        f' &nbsp;·&nbsp; '
        f'<a href="../BackLog/index.html" style="color:#e9d5ff;text-decoration:underline;">'
        f'← Back to Archive Index</a></div>'
    )
    html = html.replace("</nav>", f"</nav>{banner}", 1)

    return html


# ── BackLog/index.html builder ────────────────────────────────────────────────

def rebuild_index(archives: list[dict]) -> None:
    """Write BackLog/index.html listing all archives newest-first."""

    archives.sort(key=lambda x: x["date"], reverse=True)

    # Group by date
    by_date: dict[str, list[dict]] = {}
    for a in archives:
        by_date.setdefault(a["date"], []).append(a)

    rows_html_parts: list[str] = []
    for date_str in sorted(by_date.keys(), reverse=True):
        items = by_date[date_str]
        try:
            pretty = dt.date.fromisoformat(date_str).strftime("%B %d, %Y (%A)")
        except ValueError:
            pretty = date_str

        links = " &nbsp;&middot;&nbsp; ".join(
            f'<a href="{a["filename"]}" '
            f'style="color:#93c5fd;text-decoration:none;font-weight:500;">'
            f'{a["icon"]} {a["label"]}</a>'
            for a in sorted(items, key=lambda x: x["label"])
        )
        rows_html_parts.append(
            f"      <tr>\n"
            f'        <td style="padding:13px 18px;border-bottom:1px solid rgba(255,255,255,0.07);'
            f'color:#e8edf5;font-size:14px;white-space:nowrap;">{pretty}</td>\n'
            f'        <td style="padding:13px 18px;border-bottom:1px solid rgba(255,255,255,0.07);">'
            f"{links}</td>\n"
            f"      </tr>"
        )

    rows_html = "\n".join(rows_html_parts)
    total     = len(archives)
    num_dates = len(by_date)

    page = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>BLEE Quant — Archive Index</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    background: #0b1120; color: #e8edf5;
    -webkit-font-smoothing: antialiased; min-height: 100vh;
  }}
  nav {{
    background: #0d1829;
    border-bottom: 1px solid rgba(255,255,255,0.07);
    padding: 0 28px; height: 58px;
    display: flex; align-items: center; justify-content: space-between;
    position: sticky; top: 0; z-index: 10000;
  }}
  .nav-brand {{
    font-size: 16px; font-weight: 800; color: #fff; text-decoration: none;
    display: flex; align-items: center; gap: 6px;
  }}
  .nav-brand span {{ color: #f59e0b; }}
  .nav-links {{ display: flex; align-items: center; gap: 18px; }}
  .nav-links a {{
    color: rgba(255,255,255,0.55); font-size: 13px; text-decoration: none;
    transition: color .15s;
  }}
  .nav-links a:hover {{ color: #fff; }}
  .nav-links a.nav-cta {{
    background: #f59e0b; color: #000; padding: 5px 13px;
    border-radius: 6px; font-weight: 700;
  }}
  @media (max-width: 600px) {{
    .nav-links {{ gap: 10px; }}
    .nav-links a {{ font-size: 12px; }}
  }}
  .container {{ max-width: 860px; margin: 0 auto; padding: 44px 20px 80px; }}
  h1 {{ font-size: 26px; font-weight: 800; letter-spacing: -0.02em; margin-bottom: 8px; }}
  .sub {{
    color: rgba(255,255,255,0.45); font-size: 13px; margin-bottom: 32px;
  }}
  .card {{
    background: #131f35; border-radius: 12px;
    border: 1px solid rgba(255,255,255,0.07); overflow: hidden;
  }}
  table {{ width: 100%; border-collapse: collapse; }}
  th {{
    padding: 12px 18px; text-align: left; font-size: 11px;
    color: rgba(255,255,255,0.4); text-transform: uppercase;
    letter-spacing: 0.07em; border-bottom: 1px solid rgba(255,255,255,0.1);
  }}
  tr:last-child td {{ border-bottom: 0 !important; }}
  tr:hover td {{ background: rgba(255,255,255,0.03); }}
</style>
</head>
<body>

<div id="blee-pw-overlay" style="position:fixed;top:0;left:0;width:100%;height:100%;background:#0b1120;z-index:9999;display:flex;align-items:center;justify-content:center;">
  <div style="background:#1e293b;padding:40px;border-radius:16px;text-align:center;max-width:360px;width:90%;box-shadow:0 8px 32px rgba(0,0,0,0.5);">
    <div style="font-size:22px;font-weight:800;color:#fff;margin-bottom:6px;">&#128274; BLEE Quant Analytics</div>
    <div style="color:rgba(255,255,255,0.55);font-size:13px;margin-bottom:24px;">Archive &mdash; Subscribers Only</div>
    <input id="blee-pw-input" type="password" placeholder="Enter password"
      style="width:100%;padding:12px 16px;border-radius:8px;border:1px solid rgba(255,255,255,0.15);background:rgba(255,255,255,0.07);color:#fff;font-size:15px;margin-bottom:12px;outline:none;box-sizing:border-box;">
    <button onclick="bleePwCheck()"
      style="width:100%;padding:12px;background:#f59e0b;color:#000;font-weight:700;font-size:15px;border:none;border-radius:8px;cursor:pointer;">
      View Archive
    </button>
    <div id="blee-pw-error" style="color:#ef4444;font-size:13px;margin-top:10px;display:none;">
      Incorrect password. Please try again.
    </div>
  </div>
</div>
<script>
(function() {{
  var PW = '{PASSWORD}';
  function bleePwCheck() {{
    if (document.getElementById('blee-pw-input').value === PW) {{
      document.getElementById('blee-pw-overlay').style.display = 'none';
      sessionStorage.setItem('{SESSION_KEY}', '1');
    }} else {{
      document.getElementById('blee-pw-error').style.display = 'block';
    }}
  }}
  window.bleePwCheck = bleePwCheck;
  document.addEventListener('DOMContentLoaded', function() {{
    var inp = document.getElementById('blee-pw-input');
    if (inp) inp.addEventListener('keypress', function(e) {{ if (e.key === 'Enter') bleePwCheck(); }});
    if (sessionStorage.getItem('{SESSION_KEY}') === '1') {{
      document.getElementById('blee-pw-overlay').style.display = 'none';
    }}
  }});
}})();
</script>

<nav>
  <a class="nav-brand" href="../index.html">BLEE <span>Quant</span></a>
  <div class="nav-links">
    <a href="../index.html">Home</a>
    <a href="../marketDailySummary.html">Market Forecast</a>
    <a href="../index2.html">Daily Signal</a>
    <a href="../performance1.html">Backtest</a>
    <a href="../index.html#pricing" class="nav-cta">Subscribe</a>
  </div>
</nav>

<div class="container">
  <h1>📁 Archive Index</h1>
  <div class="sub">{total} archived report{'' if total == 1 else 's'} across {num_dates} day{'' if num_dates == 1 else 's'} &nbsp;·&nbsp; Up to 1 year of history &nbsp;·&nbsp; Newest first</div>
  <div class="card">
    <table>
      <thead>
        <tr>
          <th>Date</th>
          <th>Reports</th>
        </tr>
      </thead>
      <tbody>
{rows_html}
      </tbody>
    </table>
  </div>
</div>

</body>
</html>
"""
    (BACKLOG_DIR / "index.html").write_text(page, encoding="utf-8")
    log(f"Rebuilt BackLog/index.html — {num_dates} dates, {total} files")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    log("=== Archive started ===")
    BACKLOG_DIR.mkdir(exist_ok=True)

    today   = dt.date.today().isoformat()   # YYYY-MM-DD
    cutoff  = dt.date.today() - dt.timedelta(days=KEEP_DAYS)

    # ── Step 1: Archive each live page ────────────────────────────────────────
    for page in PAGES:
        src = page["src"]
        if not src.exists():
            log(f"  SKIP (not found): {src.name}")
            continue

        dest_name = f"{page['prefix']}_{today}.html"
        dest      = BACKLOG_DIR / dest_name

        if dest.exists():
            log(f"  Already archived today: {dest_name}")
        else:
            html = src.read_text(encoding="utf-8")
            html = patch_archive(html, page["label"], today)
            dest.write_text(html, encoding="utf-8")
            log(f"  Archived → {dest_name}")

    # ── Step 2: Prune files older than KEEP_DAYS ─────────────────────────────
    pruned = 0
    for f in BACKLOG_DIR.glob("*.html"):
        if f.name == "index.html":
            continue
        m = re.search(r"(\d{4}-\d{2}-\d{2})", f.name)
        if m:
            try:
                file_date = dt.date.fromisoformat(m.group(1))
                if file_date < cutoff:
                    f.unlink()
                    pruned += 1
                    log(f"  Pruned (>{KEEP_DAYS}d old): {f.name}")
            except ValueError:
                pass
    if pruned:
        log(f"  Total pruned: {pruned} file(s)")

    # ── Step 3: Rebuild BackLog/index.html ───────────────────────────────────
    archives: list[dict] = []
    for f in sorted(BACKLOG_DIR.glob("*.html")):
        if f.name == "index.html":
            continue
        m = re.search(r"(\d{4}-\d{2}-\d{2})", f.name)
        if not m:
            continue
        date_str = m.group(1)
        for page in PAGES:
            if f.name.startswith(page["prefix"]):
                archives.append({
                    "filename": f.name,
                    "date":     date_str,
                    "label":    page["label"],
                    "icon":     page["icon"],
                })
                break

    rebuild_index(archives)
    log("=== Archive complete ===")


if __name__ == "__main__":
    main()
