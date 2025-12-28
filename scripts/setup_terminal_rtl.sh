#!/bin/bash
# Setup script for RTL/Arabic support in iTerm2

echo "🔧 Setting up terminal for RTL/Arabic support..."
echo ""

# Check shell
SHELL_NAME=$(basename "$SHELL")
SHELL_RC="$HOME/.${SHELL_NAME}rc"

if [[ ! -f "$SHELL_RC" ]]; then
    echo "Creating $SHELL_RC..."
    touch "$SHELL_RC"
fi

# Check if settings already exist
if grep -q "LANG=en_US.UTF-8" "$SHELL_RC" 2>/dev/null; then
    echo "✅ Locale settings already exist in $SHELL_RC"
else
    echo "📝 Adding locale settings to $SHELL_RC..."
    cat >> "$SHELL_RC" << 'EOF'

# RTL/Arabic support - Added by Arabic Restaurant Agent setup
export LANG=en_US.UTF-8
export LC_ALL=en_US.UTF-8
export TERM=xterm-256color
EOF
    echo "✅ Added locale settings"
fi

# Check current locale
echo ""
echo "Current locale settings:"
locale | grep -E "LANG|LC_ALL" || echo "⚠️  Locale not set properly"

# Check terminal type
echo ""
echo "Current terminal type: $TERM"
if [[ "$TERM" == "dumb" ]]; then
    echo "⚠️  Terminal type is 'dumb' - this may cause RTL issues"
    echo "   Run: export TERM=xterm-256color"
fi

echo ""
echo "✅ Setup complete!"
echo ""
echo "Next steps:"
echo "1. Restart iTerm2 or run: source $SHELL_RC"
echo "2. Configure iTerm2: Preferences > Profiles > Text"
echo "   - Unicode normalization: NFC"
echo "   - Use Unicode version 9 widths: ✅"
echo "3. Test with: python3 scripts/test_rtl.py"
echo ""
echo "See docs/ITERM2_RTL_SETUP.md for detailed instructions"

