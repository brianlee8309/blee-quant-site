# BLEE Quant Pro Trader

A Schwab brokerage trading app for **BLEE Quant Premium/Pro subscribers**.

Connects your Schwab account to BLEE Quant's algorithmic trading signals. Sign in with your BLEE Quant account, configure your Schwab API credentials, and start trading.

---

## Quick Start

| Platform | Setup Guide |
|---|---|
| **Windows** | [windows/SETUP_WINDOWS.md](windows/SETUP_WINDOWS.md) |
| **macOS** | [mac/SETUP_MAC.md](mac/SETUP_MAC.md) |

---

## What's Included

```
client/
├── README.md                 This file
├── src/
│   ├── trader_client.py      Main trading app (Flask, port 5060)
│   ├── auth_server.py        Schwab weekly re-auth (port 8182)
│   ├── schwab_client.py      Schwab API wrapper
│   ├── token_manager.py      Encrypted token storage
│   ├── config.py             Settings loader
│   ├── requirements.txt      Python dependencies
│   └── .env.example          Credentials template — copy to .env
├── windows/
│   ├── install.bat           Install dependencies
│   ├── run.bat               Start the app
│   ├── auth_schwab.bat       Weekly Schwab re-auth
│   ├── create_shortcut.bat   Desktop shortcut
│   └── SETUP_WINDOWS.md      Full Windows setup guide
└── mac/
    ├── install.sh            Install dependencies
    ├── run.sh                Start the app
    ├── auth_schwab.sh        Weekly Schwab re-auth
    ├── create_shortcut.sh    Desktop shortcut
    └── SETUP_MAC.md          Full macOS setup guide
```

---

## Requirements

- **BLEE Quant subscription:** Premium or Pro tier ([bleeanalytics.com](https://bleeanalytics.com))
- **Schwab brokerage account:** Active account at schwab.com
- **Schwab Developer App:** Free, created at [developer.schwab.com](https://developer.schwab.com)
- **Python 3.11+**

---

## Available Symphonies (Pro Subscribers)

| Symphony | Description |
|---|---|
| BLEE-187 SGOV Bond Min Dual Reversal | Conservative bond/equity rotation strategy |
| BLEE-187 High Interest ALL in One | Higher-return strategy for high-interest environments |

Symphony allocation data is fetched live from [bleeanalytics.com](https://bleeanalytics.com) — always up-to-date, no Composer account needed.

---

## Features

- **Manual Trading** — Buy/sell any symbol, market or limit orders, regular/extended hours
- **Auto Rebalance** — One-click rebalance plan from live BLEE Quant signals
- **Portfolio View** — Real-time positions and account balance
- **Order Management** — View and cancel pending orders
- **Secure Auth** — Firebase login (your BLEE Quant account) + encrypted Schwab token

---

## Security

- Your Schwab token is encrypted at rest with a passphrase you choose
- Credentials are stored locally in `src/.env` — never leave your computer
- The app runs on `127.0.0.1` — not accessible from outside your network
- BLEE Quant login verified via Firebase (Premium/Pro tier required)

---

## Support

Questions or issues? Contact us at [bleeanalytics.com/contact](https://bleeanalytics.com/contact)
