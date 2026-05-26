# BLEE Quant Pro Trader — macOS Setup Guide

## System Requirements

| Requirement | Minimum | Notes |
|---|---|---|
| macOS | 12 Monterey or later | Intel or Apple Silicon (M1/M2/M3/M4) |
| Python | 3.11 or later | See Step 1 |
| Schwab Account | Active brokerage account | schwab.com |
| Schwab Developer App | Free API app | [developer.schwab.com](https://developer.schwab.com) |
| BLEE Subscription | Premium or Pro | [bleeanalytics.com](https://bleeanalytics.com) |
| Internet connection | Required | For BLEE data and Schwab API |

> ✅ **Apple Silicon (M1/M2/M3/M4) fully supported.** The app runs natively on ARM Macs.

---

## Step 1 — Install Python

### Option A: Download from python.org (Recommended)
1. Go to [python.org/downloads/macos](https://www.python.org/downloads/macos/)
2. Download **Python 3.11** or later
3. Open the `.pkg` file and follow the installer
4. In Terminal: `python3 --version` — should show 3.11+

### Option B: Homebrew
```bash
brew install python@3.11
```

---

## Step 2 — Get Schwab API Credentials

1. Go to [developer.schwab.com](https://developer.schwab.com) and sign in
2. Click **My Apps → Add Application**
3. Fill in the form:
   - App Name: anything (e.g. "My Trader")
   - Callback URL: `https://127.0.0.1:8182`
4. After approval, click your app to see **App Key** and **App Secret**
5. Save both — you'll need them in Step 4

---

## Step 3 — Make Scripts Executable and Install

Open **Terminal** and run:

```bash
# Navigate to the client folder (adjust path as needed)
cd ~/Downloads/client

# Make all shell scripts executable
chmod +x mac/*.sh

# Run the installer
bash mac/install.sh
```

The installer creates a Python virtual environment in `src/venv/` and installs all packages. This takes 1–2 minutes.

---

## Step 4 — Configure Your Credentials

Open `src/.env` in any text editor (TextEdit, VS Code, etc.) and fill in:

```
SCHWAB_API_KEY=your_app_key_here
SCHWAB_APP_SECRET=your_app_secret_here
SCHWAB_ACCOUNT_NUMBER=12345678
SCHWAB_TOKEN_PASSPHRASE=choose_any_passphrase
SCHWAB_CALLBACK_URL=https://127.0.0.1:8182
PORTFOLIO_VALUE=10000.00
```

- **SCHWAB_API_KEY** — App Key from developer.schwab.com
- **SCHWAB_APP_SECRET** — App Secret from developer.schwab.com
- **SCHWAB_ACCOUNT_NUMBER** — Your Schwab brokerage account number
- **SCHWAB_TOKEN_PASSPHRASE** — Any passphrase you choose (encrypts your token)
- **PORTFOLIO_VALUE** — Your rebalancing budget in dollars

You can also configure these in the **Settings** tab inside the app.

---

## Step 5 — Authenticate with Schwab (One-Time Setup)

**Repeat this weekly when your token expires.**

```bash
bash mac/auth_schwab.sh
```

1. Your browser opens automatically
2. Click **"Sign in with Schwab"**
3. Browser shows a security warning — click **Advanced → Proceed to 127.0.0.1** (this is safe, it's local)
4. Log in with your Schwab credentials and complete 2-factor authentication
5. You'll see "Authenticated successfully"
6. Close the browser tab and press **Ctrl+C** in Terminal

The token is saved encrypted at `src/schwab_token.enc`.

---

## Step 6 — Start the App

```bash
bash mac/run.sh
```

Your browser opens automatically at `http://127.0.0.1:5060`. Sign in with your **BLEE Quant account**.

---

## Step 7 — Create a Desktop Shortcut (Optional)

```bash
bash mac/create_shortcut.sh
```

This creates a double-clickable launcher on your Desktop. If macOS blocks it the first time, right-click → Open → Open.

---

## Weekly Schwab Re-Authentication

Schwab tokens expire every **7 days**. When the app shows a Schwab connection error:

```bash
# Stop the app first (Ctrl+C in its terminal), then:
bash mac/auth_schwab.sh
# Then restart:
bash mac/run.sh
```

---

## Using the App

### Trade Tab
Place manual buy/sell orders. Supports market and limit orders, pre/after-hours sessions, and day/GTC duration.

### Rebalance Tab
Compute a rebalance plan from live BLEE Quant symphony data:
1. Select a symphony from the dropdown
2. Enter your budget
3. Click **Compute Plan** — fetches live data from bleeanalytics.com
4. Review the plan → **Execute All Sells** → **Execute All Buys**

### Positions Tab
View your current holdings and account balance.

### Orders Tab
View and cancel pending orders.

### Settings Tab
Update your Schwab API credentials and portfolio budget without editing files.

---

## Troubleshooting

**Permission denied running .sh files**
```bash
chmod +x mac/*.sh
```

**Python 3.11+ not found**  
Install from [python.org](https://python.org) or via Homebrew: `brew install python@3.11`

**"No Schwab token found"**  
Run `bash mac/auth_schwab.sh`

**Browser certificate warning during auth**  
Expected. Click Advanced → Proceed to 127.0.0.1 (local connection, safe).

**"Access denied" on BLEE login**  
Your subscription must be Premium or higher. Check at bleeanalytics.com.

**App opens but can't connect to Schwab**  
Check that `src/.env` has all four required fields filled in.

**M1/M2/M3 Mac: some packages fail to install**  
Try: `arch -arm64 pip install -r requirements.txt` inside the `src/` folder with the venv activated.

---

## File Structure

```
client/
├── src/
│   ├── trader_client.py      Main app (runs at :5060)
│   ├── auth_server.py        Weekly Schwab re-auth (runs at :8182)
│   ├── schwab_client.py      Schwab API helper
│   ├── token_manager.py      Encrypted token storage
│   ├── config.py             Configuration loader
│   ├── requirements.txt      Python packages
│   ├── venv/                 Python virtual environment (created by install.sh)
│   ├── .env                  Your credentials ⚠️ DO NOT SHARE
│   └── schwab_token.enc      Encrypted Schwab token ⚠️ DO NOT SHARE
└── mac/
    ├── install.sh            Step 3
    ├── run.sh                Start the app
    ├── auth_schwab.sh        Step 5 (weekly)
    ├── create_shortcut.sh    Optional desktop shortcut
    └── SETUP_MAC.md          This file
```

---

## Security Notes

- **Never share** `src/.env` or `src/schwab_token.enc`
- The token file is encrypted with your passphrase — keep it safe
- The app runs entirely on your Mac — no trading data is sent to BLEE servers
- Symphony allocation data is fetched read-only from bleeanalytics.com
- If you suspect your credentials are compromised, regenerate your Schwab app secret at developer.schwab.com
