
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
