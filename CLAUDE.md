
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
- Task name: "IBKR Daily Rebalan