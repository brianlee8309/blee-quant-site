# Composer Daily ETF Allocation + BLEE Stock Analysis Dashboard

This package does two things every weekday at 3:50 PM ET:

1. Pulls the current ETF allocation for your Composer brokerage account, enriches it with live Yahoo Finance prices, and appends one row per ETF per day to a CSV.
2. Re-renders a self-contained `index.html` dashboard ("BLEE Stock Analysis — Daily Update") with a pie chart, portfolio value over time, holdings table, annualized return, and a stacked-area history of weight changes.

You can then upload `index.html` (and optionally `composer_allocations.csv`) to a static host like GitHub Pages, Netlify, Cloudflare Pages, or your own web server.

## Why this runs on your machine, not on Cowork

Cowork's secure sandbox does not allowlist `api.composer.trade` or `query1.finance.yahoo.com`, so any scheduled task running here cannot reach those APIs. The cleanest fix is to schedule the script with your operating system's built-in scheduler. It needs only Python 3.9+ and runs in seconds.

## Files in this folder

- `composer_pull_allocation.py` — the script (puller + dashboard generator)
- `composer_config.json` — your API key, secret, account UUID, and a list of Symphonies to track
- `dashboard_template.html` — HTML template the script populates with your data

After it runs, for each Symphony in your config it will create / refresh:

- `<csv>` — that Symphony's history, one row per ETF per day (e.g. `composer_allocations.csv`, `composer_allocations_185.csv`)
- `<csv-stem>_YYYY-MM-DD.json` — that Symphony's slice of today's API response
- `<html>` — that Symphony's rendered dashboard (e.g. `index.html`, `index2.html`)

Plus, once per run:

- `composer_symphony_stats_YYYY-MM-DD.json` — the full `symphony-stats-meta` API response (all Symphonies)
- `composer_run.log` — run log

## Tracking multiple Symphonies

The `symphonies` list in `composer_config.json` lets you track any number of Symphonies in parallel. Each entry needs:

- `id` — the Symphony ID (find it in Composer's URL: `app.composer.trade/portfolio?factsheet=<id>`)
- `name` — display name shown on the dashboard subtitle
- `csv` — output CSV filename (kept in this folder)
- `html` — output dashboard HTML filename (kept in this folder)

Add a new Symphony by appending an entry:

```json
{
  "id": "newSymphonyIdHere",
  "name": "My New Strategy",
  "csv": "composer_allocations_new.csv",
  "html": "index3.html"
}
```

The script makes one API call per run regardless of how many Symphonies you list (the `symphony-stats-meta` endpoint returns all of them at once), then filters client-side by `id`.

## One-time setup

1. Copy all three files (`composer_pull_allocation.py`, `composer_config.json`, `dashboard_template.html`) into a folder on your computer. They must live in the same folder. Suggested location:
   - Windows: `C:\Kei\ComposerInvest\`
   - macOS / Linux: `~/composer-tracker/`

2. Confirm you have Python 3.9+ installed:
   ```
   python3 --version
   ```
   On Windows, this might be `python --version` instead.

3. Test the script manually:
   ```
   cd C:\Kei\ComposerInvest      # or your folder
   python composer_pull_allocation.py
   ```
   You should see log lines and four new files appear: `composer_allocations.csv`, `composer_raw_<date>.json`, `composer_run.log`, and `index.html`.

4. Open `index.html` in a browser to confirm the dashboard renders. The first day will only show one data point on the line chart and "needs ≥ 14 days" for annualized return — that's expected. Both fill in as days accumulate.

## Schedule — Windows (Task Scheduler)

1. Open Task Scheduler → "Create Basic Task..."
2. Trigger: Weekly, Monday–Friday, start time 3:50 PM
3. Action: Start a program
   - Program/script: full path to `python.exe`, e.g. `C:\Python312\python.exe`. Find it with `where python` in cmd.
   - Add arguments: `composer_pull_allocation.py`
   - Start in: `C:\Kei\ComposerInvest`
4. In the task's **Properties → General**, check "Run whether user is logged on or not".
5. If your machine is not on Eastern Time, set the trigger to the local clock time that corresponds to 3:50 PM ET (e.g. 12:50 PM if you're on Pacific).

## Schedule — macOS (launchd)

Create `~/Library/LaunchAgents/com.composer.daily.plist`:
```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.composer.daily</string>
  <key>ProgramArguments</key>
  <array>
    <string>/usr/bin/python3</string>
    <string>/Users/YOUR_USERNAME/composer-tracker/composer_pull_allocation.py</string>
  </array>
  <key>StartCalendarInterval</key>
  <array>
    <dict><key>Weekday</key><integer>1</integer><key>Hour</key><integer>15</integer><key>Minute</key><integer>50</integer></dict>
    <dict><key>Weekday</key><integer>2</integer><key>Hour</key><integer>15</integer><key>Minute</key><integer>50</integer></dict>
    <dict><key>Weekday</key><integer>3</integer><key>Hour</key><integer>15</integer><key>Minute</key><integer>50</integer></dict>
    <dict><key>Weekday</key><integer>4</integer><key>Hour</key><integer>15</integer><key>Minute</key><integer>50</integer></dict>
    <dict><key>Weekday</key><integer>5</integer><key>Hour</key><integer>15</integer><key>Minute</key><integer>50</integer></dict>
  </array>
  <key>EnvironmentVariables</key>
  <dict><key>TZ</key><string>America/New_York</string></dict>
</dict>
</plist>
```

Then load it:
```
launchctl load ~/Library/LaunchAgents/com.composer.daily.plist
```

## Schedule — Linux (cron)

Open your crontab:
```
crontab -e
```

Add this line:
```
50 15 * * 1-5  TZ=America/New_York /usr/bin/python3 /home/YOU/composer-tracker/composer_pull_allocation.py
```

This fires at 3:50 PM ET, Monday–Friday.

## Hosting the dashboard

Each run regenerates `index.html` in place. The file is fully self-contained (HTML + CSS + JS + embedded data) — the only external request is to the Chart.js CDN, which is fine on any static host.

### Option A — GitHub Pages (free, version-controlled)

One-time:
1. Create a new public or private repo on GitHub, e.g. `blee-stock-analysis`.
2. Settings → Pages → Source: select "Deploy from a branch", branch `main`, folder `/ (root)`.
3. Clone it locally: `git clone https://github.com/YOU/blee-stock-analysis.git`

Daily auto-deploy: in the same folder as your scheduled script, add a small batch/shell script that runs after the puller:
```
cd C:\Kei\ComposerInvest
copy /Y index.html ..\blee-stock-analysis\index.html
copy /Y composer_allocations.csv ..\blee-stock-analysis\composer_allocations.csv
cd ..\blee-stock-analysis
git add index.html composer_allocations.csv
git commit -m "daily update %DATE%"
git push
```
Save as `deploy_dashboard.bat` and add it as a second action on the Task Scheduler task (or chain it in the same .bat).

Your page will be at `https://YOU.github.io/blee-stock-analysis/`.

### Option B — Netlify drag-and-drop (no git needed)

1. Sign up at netlify.com.
2. From your Sites page, drag the folder containing `index.html` and `composer_allocations.csv` onto the upload area.
3. Netlify gives you a URL like `https://blee-stock-analysis.netlify.app/`.
4. To redeploy, just drop the updated folder again. (Or install the Netlify CLI and run `netlify deploy --prod --dir .` from your scheduled batch script.)

### Option C — Your own server / S3 / Cloudflare Pages

Anything that serves static files works. Just upload `index.html` and `composer_allocations.csv` to the directory your domain points at. The CSV download link in the dashboard is relative (`composer_allocations.csv`), so they should sit in the same directory.

## Verifying it works

After the first scheduled run:
- Open `composer_allocations.csv` — you should see one row per ETF, with `weight_pct` summing to ~100 and non-empty `market_value`.
- Open `index.html` in a browser — pie chart, holdings table, and the line chart should populate. Day-change/total-return show "—" until you have at least 2 days; annualized-return shows "needs ≥ 14 days" until 14 days are present.
- Check `composer_run.log` for any errors.

If you see HTTP 401 or 403 on the API call: re-check `api_key` / `api_secret` in `composer_config.json`.

## Caveats / current limitations

- **Per-Symphony view via `symphony-stats-meta` endpoint.** The script calls `GET /api/v0.1/portfolio/accounts/{uuid}/symphony-stats-meta` and filters the returned `symphonies` list to the `symphony_id` set in `composer_config.json`. Holdings come back with weight (`allocation`), shares (`amount`), and market value (`value`) directly — no Yahoo Finance enrichment needed. To track a different Symphony, just change the `symphony_id` in the config (find it in the URL: `app.composer.trade/portfolio?factsheet=<symphony_id>`).
- **Yahoo Finance fallback.** If Composer's endpoint ever fails, the script falls back to whole-account `/holdings` and prices from Yahoo. You'll see `source=account-holdings+yahoo-prices` in the CSV in that case.
- **Annualized return needs ≥ 14 trading days of history.** With fewer days the dashboard shows "needs ≥ 14 days".

## Security

`composer_config.json` contains your live API secret. Keep it:
- Out of any cloud-synced or public folder
- Not committed to git (add `composer_config.json` to `.gitignore` in the deploy repo)
- Readable only by you: on macOS/Linux, `chmod 600 composer_config.json`

If you suspect the secret has leaked, revoke it from Composer's settings and generate a new one. As a precaution, since this config has been transmitted through Cowork, consider rotating the secret once you have everything running locally.

## Want a different schedule?

Edit the cron / launchd / Task Scheduler entry. Common alternatives:
- **3:55 PM ET** (closer to close): change `50 15` → `55 15`
- **4:30 PM ET** (post-rebalance): change `50 15` → `30 16`
- **Both pre- and post-close**: add a second cron line at `30 16 * * 1-5`
