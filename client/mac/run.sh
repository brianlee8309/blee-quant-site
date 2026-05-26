#!/bin/bash
# BLEE Quant Pro Trader — macOS Launcher

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SRC_DIR="$(dirname "$SCRIPT_DIR")/src"

cd "$SRC_DIR" || { echo "[ERROR] src/ folder not found"; exit 1; }

# Check for .env
if [ ! -f ".env" ]; then
    echo "[ERROR] .env not found in src/"
    echo "Run mac/install.sh first, then edit src/.env with your credentials."
    exit 1
fi

# Activate virtualenv if it exists
if [ -d "venv" ]; then
    source venv/bin/activate
fi

# Warn if no token
if [ ! -f "schwab_token.enc" ]; then
    echo ""
    echo "[WARNING] No Schwab token found."
    echo "Run mac/auth_schwab.sh first to authenticate with Schwab."
    echo ""
    echo "Starting anyway — you can configure settings in the app."
    echo ""
    sleep 2
fi

echo "Starting BLEE Quant Pro Trader..."
echo "Open http://127.0.0.1:5060 in your browser."
echo "Press Ctrl+C to stop."
echo ""

python3 trader_client.py
