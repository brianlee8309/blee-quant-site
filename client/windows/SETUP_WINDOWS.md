# BLEE Quant Pro Trader — Windows Setup Guide

## System Requirements

| Requirement | Minimum | Notes |
|---|---|---|
| Windows | 10 or 11 | 64-bit |
| Python | 3.11 or later | [python.org/downloads](https://www.python.org/downloads/) |
| Schwab Account | Active brokerage account | schwab.com |
| Schwab Developer App | Free API app | [developer.schwab.com](https://developer.schwab.com) |
| BLEE Subscription | Premium or Pro | [bleeanalytics.com](https://bleeanalytics.com) |
| Internet connection | Required | For BLEE data and Schwab API |

---

## Step 1 — Install Python

1. Go to [python.org/downloads](https://www.python.org/downloads/)
2. Download **Python 3.11** or later (the button at the top)
3. Run the installer — **check "Add Python to PATH"** at the bottom of the first screen
4. Click "Install Now"
5. Verify: open Command Prompt and type `python --version` — should show 3.11+

---

## Step 2 — Get Schwab API Credentials

You need a free Schwab developer app to connect the trader to your account.

1. Go to [developer.schwab.com](https://developer.schwab.com) and sign in with your Schwab account
2. Click **My Apps → Add Application**
3. Fill in the form:
   - App Name: anything (e.g. "My Trader")
   - Callback URL: `https://127.0.0.1:8182`
4. After approval (usually instant), click your app to see:
   - **App Key** (this is your API Key)
   - **App Secret**
5. Save both — you'll need them in Step 4

---

## Step 3 — Install the Trader App

1. Double-click `windows\install.bat`
2. It will download and install the required Python packages
3. Wait for "Installation complete!" (usually 1–2 minutes)

---

## Step 4 — Configure Your Credentials

Open `src\.env` in Notepad (or any text editor) and fill in your values:

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
- **SCHWAB_ACCOUNT_NUMBER** — Your 8-digit Schwab account number
- **SCHWAB_TOKEN_PASSPHRASE** — Any secure passphrase you choose (encrypts your token file)
- **PORTFOLIO_VALUE** — Your trading budget in dollars

You can also set these in the **Settings** tab inside the app later.

---

## Step 5 — Authenticate with Schwab (One-Time Setup)

This step connects the app to your Schwab account. **Repeat this weekly** when prompted.

1. Double-click `windows\auth_schwab.bat`
2. Your browser opens — click **"Sign in with Schwab"**
3. Your browser will warn about a certificate — click **Advanced → Proceed to 127.0.0.1**
4. Log in with your Schwab credentials and complete 2-factor authentication
5. You'll see a "Authenticated successfully" page
6. Close the browser tab and press **Ctrl+C** in the terminal window

The token is saved encrypted in `src\schwab_token.enc`. **Do not delete this file.**

---

## Step 6 — Start the App

1. Double-click `windows\run.bat` (or the desktop shortcut if you created one)
2. Your browser opens automatically at `http://127.0.0.1:5060`
3. Sign in with your **BLEE Quant account** (the one you use on bleeanalytics.com)
4. You're in!

---

## Step 7 — Create a Desktop Shortcut (Optional)

Double-click `windows\create_shortcut.bat` to add a "BLEE Quant Pro Trader" shortcut to your desktop.

---

## Weekly Schwab Re-Authentication

Schwab tokens expire every **7 days**. When the app shows a token error:

1. Stop the app (close the terminal window or press Ctrl+C)
2. Run `windows\auth_schwab.bat`
3. Complete the Schwab login again
4. Start the app again with `windows\run.bat`

---

## Using the App

### Trade Tab
Place manual buy/sell orders. Supports market and limit orders, pre/after-hours sessions, and day/GTC duration.

### Rebalance Tab
Automatically compute a rebalance plan based on your selected BLEE Quant symphony:
1. Select a symphony from the dropdown
2. Enter your budget (portfolio value in dollars)
3. Click **Compute Plan** — the plan fetches live data from bleeanalytics.com
4. Review the plan, then click **Execute All Sells** → **Execute All Buys**

### Positions Tab
View your current holdings and account balance.

### Orders Tab
View and cancel pending orders.

### Settings Tab
Update your Schwab API credentials and portfolio budget without editing files.

---

## Troubleshooting

**"Schwab not configured" error**
→ Check that `src\.env` has your API key, secret, and passphrase filled in.

**"No Schwab token found"**
→ Run `windows\auth_schwab.bat` to authenticate.

**Browser shows "Proceed" warning during auth**
→ This is expected. Click Advanced → Proceed to 127.0.0.1 (the connection is local-only).

**"Access denied" on login**
→ Your BLEE Quant subscription must be Premium or higher. Check at bleeanalytics.com.

**App won't start — Python not found**
→ Reinstall Python and make sure to check "Add Python to PATH" during installation.

**"pip is not recognized"**
→ Same as above — Python wasn't added to PATH. Reinstall Python with the PATH option checked.

---

## File Structure

```
client/
├── src/
│   ├── trader_client.py      Main app
│   ├── auth_server.py        Weekly Schwab re-auth
│   ├── schwab_client.py      Schwab API helper
│   ├── token_manager.py      Encrypted token storage
│   ├── config.py             Configuration loader
│   ├── requirements.txt      Python packages
│   ├── .env                  Your credentials (DO NOT SHARE)
│   └── schwab_token.enc      Encrypted Schwab token (DO NOT SHARE)
└── windows/
    ├── install.bat            Step 3
    ├── run.bat                Start the app
    ├── auth_schwab.bat        Step 5 (weekly)
    ├── create_shortcut.bat    Optional desktop shortcut
    └── SETUP_WINDOWS.md       This file
```

---

## Security Notes

- **Never share** your `src\.env` or `src\schwab_token.enc` files
- The token file is encrypted with your passphrase — keep the passphrase safe
- The app runs entirely on your computer — no data is sent to BLEE servers
- Symphony allocation data is fetched from bleeanalytics.com (read-only)
