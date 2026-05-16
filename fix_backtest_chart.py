"""
fix_backtest_chart.py
─────────────────────
One-shot repair for Algorithm185History.html. Restores accuracy stats +
backtest chart by reading the JS tail from chart_and_stats.html.

Run ONCE on Windows whenever the page goes blank:
    cd C:\\Kei\\ComposerInvest
    python fix_backtest_chart.py
"""
from pathlib import Path
import re

HERE = Path(__file__).parent
HTML = HERE / "Algorithm185History.html"
TAIL_FILE = HERE / "chart_and_stats.html"

if not TAIL_FILE.exists():
    print(f"ERROR: missing {TAIL_FILE.name}")
    raise SystemExit(1)

text = HTML.read_text(encoding="utf-8")

m = re.search(r"^// ── PRICE_DATA_START.*$", text, flags=re.MULTILINE)
if m is None:
    m = re.search(r"^const PRICE_DATA = .*$", text, flags=re.MULTILINE)
if m is None:
    print("ERROR: PRICE_DATA marker not found in Algorithm185History.html")
    raise SystemExit(1)

prefix = text[: m.start()].rstrip() + "\n"
tail = TAIL_FILE.read_text(encoding="utf-8")

new = prefix + tail
HTML.write_text(new, encoding="utf-8")
print(f"Wrote {HTML.name}: {len(new):,} chars")
print()
print("Refresh the page (Ctrl+Shift+R). You should see:")
print("  - Two-line chart (green BLEE + pink SPY)")
print("  - Bearish/Bullish day counts populated")
print("  - Accuracy 1yr/3yr percentages")
print()
print("Re-run update_accuracy.py + push to GitHub:")
print("  python update_accuracy.py")
print("  git add Algorithm185History.html chart_and_stats.html")
print('  git commit -m "Restore backtest chart + accuracy stats"')
print("  git push origin main")
