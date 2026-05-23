#!/bin/bash
# BLEE Quant Pro Trader — macOS Installer

set -e

echo ""
echo " ============================================"
echo "  BLEE Quant Pro Trader — macOS Install"
echo " ============================================"
echo ""

# ── Check Python 3.11+ ────────────────────────────────────────────────────────
PYTHON=""
for cmd in python3.13 python3.12 python3.11 python3 python; do
    if command -v "$cmd" &>/dev/null; then
        VER=$("$cmd" -c "import sys; print(sys.version_info[:2])" 2>/dev/null)
        if "$cmd" -c "import sys; sys.exit(0 if sys.version_info >= (3,11) else 1)" 2>/dev/null; then
            PYTHON="$cmd"
            echo " Found: $("$cmd" --version)"
            break
        fi
    fi
done

if [ -z "$PYTHON" ]; then
    echo " [ERROR] Python 3.11 or later not found."
    echo ""
    echo " Install options:"
    echo "   Option 1 (recommended): https://python.org/downloads"
    echo "   Option 2 (Homebrew):    brew install python@3.11"
    echo ""
    exit 1
fi

# ── Navigate to src folder ────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SRC_DIR="$(dirname "$SCRIPT_DIR")/src"

if [ ! -d "$SRC_DIR" ]; then
    echo " [ERROR] src/ folder not found at $SRC_DIR"
    exit 1
fi

cd "$SRC_DIR"
echo " Installing from: $SRC_DIR"
echo ""

# ── Create virtualenv (recommended on macOS) ──────────────────────────────────
if [ ! -d "venv" ]; then
    echo " Creating Python virtual environment..."
    "$PYTHON" -m venv venv
    echo " Virtual environment created."
fi

# Activate venv
source venv/bin/activate

# ── Install packages ──────────────────────────────────────────────────────────
echo ""
echo " Installing Python packages..."
echo " (This may take 1–2 minutes on first run)"
echo ""

pip install --quiet --upgrade pip
pip install -r requirements.txt

# ── Copy .env.example if .env doesn't exist ───────────────────────────────────
if [ ! -f ".env" ] && [ -f ".env.example" ]; then
    cp ".env.example" ".env"
    echo ""
    echo " Created src/.env from template."
    echo " Edit src/.env with your Schwab credentials."
fi

echo ""
echo " ============================================"
echo "  Installation complete!"
echo " ============================================"
echo ""
echo " Next steps:"
echo "  1. Edit src/.env with your Schwab API credentials"
echo "  2. Run: mac/auth_schwab.sh    (one-time Schwab login)"
echo "  3. Run: mac/run.sh            (start the trading app)"
echo ""
echo " Or run create_shortcut.sh to add a dock/desktop shortcut."
echo ""
