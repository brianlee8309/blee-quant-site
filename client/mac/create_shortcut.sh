#!/bin/bash
# BLEE Quant Pro Trader — Create macOS App Shortcut

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
RUN_SH="$SCRIPT_DIR/run.sh"
APP_NAME="BLEE Quant Pro Trader"
DESKTOP="$HOME/Desktop"
APPS="$HOME/Applications"

# Make sure run.sh is executable
chmod +x "$RUN_SH"

echo ""
echo " Creating macOS shortcut for $APP_NAME..."
echo ""

# ── Option 1: Create a .command file on the Desktop ──────────────────────────
COMMAND_FILE="$DESKTOP/$APP_NAME.command"

cat > "$COMMAND_FILE" << EOF
#!/bin/bash
# $APP_NAME launcher
cd "$(dirname "$RUN_SH")"
bash "$RUN_SH"
EOF

chmod +x "$COMMAND_FILE"

echo " Created desktop launcher: $COMMAND_FILE"
echo ""
echo " To use it:"
echo "  • Double-click '$APP_NAME' on your Desktop"
echo "  • If macOS says it cannot be opened (Gatekeeper):"
echo "    Right-click the file → Open → Open"
echo ""

# ── Option 2: Create an Automator-style .app (if possible) ───────────────────
APP_BUNDLE="$DESKTOP/$APP_NAME.app"
CONTENTS="$APP_BUNDLE/Contents"
MACOS_DIR="$CONTENTS/MacOS"
mkdir -p "$MACOS_DIR"

cat > "$CONTENTS/Info.plist" << 'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleExecutable</key>
    <string>launcher</string>
    <key>CFBundleIdentifier</key>
    <string>com.bleequant.pro-trader</string>
    <key>CFBundleName</key>
    <string>BLEE Quant Pro Trader</string>
    <key>CFBundleVersion</key>
    <string>1.0</string>
    <key>LSUIElement</key>
    <false/>
</dict>
</plist>
PLIST

cat > "$MACOS_DIR/launcher" << EOF
#!/bin/bash
open -a Terminal "$RUN_SH"
EOF

chmod +x "$MACOS_DIR/launcher"

echo " Also created app bundle: $APP_BUNDLE"
echo " Double-click it to launch in a Terminal window."
echo ""
echo " TIP: Drag either shortcut to your Dock for quick access."
echo ""
