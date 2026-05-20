
## ⚠️ CRITICAL: Large File Edit Rules

**Algorithm185History.html is ~1,445 lines. The Edit tool SILENTLY TRUNCATES files this large.**

Rules that MUST be followed for any edit to Algorithm185History.html (or any HTML file >800 lines):
1. **NEVER use the Edit tool** on Algorithm185History.html — use Python (`sed` or string replacement) instead
2. After any Python write, immediately run: `python verify_html.py`
3. After any write, always verify: `wc -l Algorithm185History.html` (must be ≥ 1,350) and `tail -5 Algorithm185History.html` (must end with `</html>`)
4. The update scripts (update_accuracy.py, update_performance.py) already call verify_html.py automatically

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
- Location: C:\Kei\VisualStudio\SchwabTrader\trader_ui.py
- Launcher: trader_ui.bat (desktop shortcut "Schwab Trader")
- URL: http://127.0.0.1:5050
- Built by Opus 4.7 in a separate session
- Features: Buy/Sell, Market/Limit, Session (Regular/AM/PM/Seamless), Duration (Day/GTC), Symbol, Qty, Limit price, Get Quote, Review & Submit modal, pending orders panel with Cancel
- Enforces: Market orders = NORMAL session only; GTC = NORMAL session only (Schwab API EXTO limitation)
- Future integration: "Import from Composer" button — reads composer_allocations_185_3yr2.csv or index2.html, computes target shares from weight_pct × portfolio_value / price, diffs vs current positions, pre-fills or batch-submits trades

## Two Trading Systems in Parallel
- IBKR: ibkr_trader.py → reads index2.html → auto-trades U25734106 at 3:55 PM ET via TWS
- Schwab: trader_ui.py → manual web UI at :5050 → future CSV/index2.html import planned
- Both share the same Composer signal source: symphony qjmHJ3IR19kmaAlbgkNj → index2.html
