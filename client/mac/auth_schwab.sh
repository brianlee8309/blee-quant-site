#!/bin/bash
# BLEE Quant Pro Trader — Schwab Weekly Re-Authentication (macOS)

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SRC_DIR="$(dirname "$SCRIPT_DIR")/src"

cd "$SRC_DIR" || { echo "[ERROR] src/ folder not found"; exit 1; }

if [ -d "venv" ]; then
    source venv/bin/activate
fi

echo ""
echo " ============================================"
echo "  Schwab Weekly Re-Authentication"
echo " ============================================"
echo ""
echo " Your browser will open shortly."
echo " Click 'Sign in with Schwab' and complete the 2FA login."
echo " After success, close the browser tab and press Ctrl+C here."
echo ""
echo " NOTE: Your browser will show a security warning about the"
echo " self-signed certificate. Click 'Advanced' then 'Proceed'."
echo " This is expected and safe — it's a local connection only."
echo ""

python3 auth_server.py
