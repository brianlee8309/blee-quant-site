
## ⚠️ CRITICAL: Large File Edit Rules

**The Edit tool SILENTLY TRUNCATES large files (any file >~800 lines). This affects HTML and Python files alike.**

Confirmed affected files:
- `Algorithm185History.html` (~1,445 lines) — HTML
- `trader_ui.py` (~2,119 lines) — Python

Rules that MUST be followed for ANY file over ~800 lines:
1. **NEVER use the Edit tool** — use Python string replacement via bash instead
2. After any write, always verify: `wc -l <file>` and `tail -8 <file>` (must end with complete code, not mid-string or mid-comment)
3. Run `python3 -m py_compile <file>` for Python files to catch syntax errors immediately

For Algorithm185History.html specifically:
- After any Python write, run: `python verify_html.py`
- Must be ≥ 1,350 lines and end with `</html>`
- The update scripts (update_accuracy.py, update_performance.py) already call verify_html.py automatically

**How to safely edit Algorithm185History.html:**
```python
# Read → modify in memory → write back (NEVER use the Edit tool)
content = open('Algorithm185History.html', encoding='utf-8').read()
content = content.replace('OLD_TEXT', 'NEW_TEXT')
open('Algorithm185History.html', 'w', encoding='utf-8').write(content)
# Then verify:
import subprocess; subprocess.run(['python', 'verify_html.py'])
```

**Why this happened:** Claude's Edit tool loaded the file, made the replacement, but silently dropped the last ~130 lines when writing. The file committed and deployed in a broken state, causing stats, the chart, and the full history table to all show blank/missing data.

## IBKR Windows Scheduled Task
- Task name: "IBKR Daily Rebalance"
- Bat file: C:\Kei\ComposerInvest\run_ibkr.bat
- Scheduled time: **3:55 PM ET** (user confirmed, not 3:58 PM)
- Runs AFTER "Composer Daily Allocation Pull" (run_signal.bat at 3:51 PM)
- Distribution source: index2.html → symphony qjmHJ3IR19kmaAlbgkNj
- Account: U25734106 (live, TWS port 7496)

## Schwab Trader Web App
- Location: C:\Kei\VisualStudio\SchwabTrader\trader_ui.py (~2,119 lines; use Python string replace for edits, NOT Edit tool)
- Launcher: trader_ui.bat (desktop shortcut "Schwab Trader")
- URL: http://127.0.0.1:5050
- Features: Buy/Sell, Market/Limit, Session (Regular/AM/PM/Seamless), Duration (Day/GTC), Symbol, Qty, Limit price, Get Quote, Review & Submit modal, pending orders panel with Cancel
- Enforces: Market orders = NORMAL session only; GTC = NORMAL session only (Schwab API EXTO limitation)

### Symphony Dropdown (Blee Quant Analytics Rebalance section)
- Fetches from https://bleeanalytics.com/CurrentWatchSymphony.html via `api_composer_symphonies()` (requests.get, server-side, no auth needed)
- Parses `/* __SYMPHONY_DATA__ */` marker to extract SYMPHONIES JSON array
- `opt.value` = stable allocation filename (from `_STABLE_JSON_MAP`), e.g. `composer_allocations_186main.json`
- `opt.dataset.symphId` = symphony UUID
- Hidden from dropdown: `qjmHJ3IR19kmaAlbgkNj` (IBKR/Daily Signal only)
- PRO tier only: `iPifD8uTozTr0sbu9qiB`
- Admin sees all non-hidden symphonies
- Fallback: if site unreachable, builds placeholder list from composer_config.json

### Compute Rebalance Plan (`api_composer_plan()`)
- PRIMARY source: fetches allocations from bleeanalytics.com/CurrentWatchSymphony.html
  - Reverse-maps filename → symphony_id via `_REVERSE_MAP`
  - Finds that symphony in SYMPHONIES JSON; converts `holdings[].pct` → `weight_pct`
  - This is always up-to-date (page updated at 3:51 PM ET by composer_pull_allocation.py)
- FALLBACK: reads local stable JSON file (composer_loader.load_file) if site unreachable
- Response includes `"source": "bleeanalytics.com"` or `"local"` field
- **Orphan SELL ALL**: after compute_plan(), scans current account positions for any symbol not in the symphony and not exempt → adds SELL ALL row (weight%=0, target=0, delta=−full qty). Handles legacy holdings like VIXY automatically.
- **Sort**: plan rows sorted by weight% descending; excluded rows at bottom
- **Summary footer**: shows "Symphony positions target: $X ✓" + net cash from trades + account cash after trades (not the confusing Portfolio−Cash formula)

### Auto-rebalance (schwab_rebalance.py, 3:54 PM ET)
- Reads `rebalance_config.json` → `allocation_file` → calls `composer_loader.load_file()`
- Local stable JSON files exist after 3:51 PM daily (written by composer_pull_allocation.py)
- Falls back to blee_signal_fetcher (remote BLEE site) if local file missing

### Config files (C:\Kei\VisualStudio\SchwabTrader\)
- `rebalance_config.json`: `{"budget": 32900.0, "allocation_file": "composer_allocations_186main.json"}`
- `composer_config.json`: same file as C:\Kei\ComposerInvest\composer_config.json (read-only reference)

## Two Trading Systems in Parallel
- IBKR: ibkr_trader.py → reads index2.html → auto-trades U25734106 at 3:55 PM ET via TWS (symphony qjmHJ3IR19kmaAlbgkNj)
- Schwab: schwab_rebalance.py → reads rebalance_config.json → auto-trades at 3:54 PM ET (symphony selected in UI)
- Schwab UI: trader_ui.py → manual web UI at :5050 → "Compute Rebalance Plan" fetches from bleeanalytics.com
