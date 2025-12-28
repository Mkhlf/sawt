#!/usr/bin/env python3
"""
Setup script for RTL/Arabic support in iTerm2 (Python version).
"""
import os
import subprocess
from pathlib import Path

def main():
    print("🔧 Setting up terminal for RTL/Arabic support...")
    print()
    
    # Get shell and config file
    shell = os.environ.get("SHELL", "/bin/zsh")
    shell_name = Path(shell).name
    shell_rc = Path.home() / f".{shell_name}rc"
    
    # Create config file if it doesn't exist
    if not shell_rc.exists():
        print(f"Creating {shell_rc}...")
        shell_rc.touch()
    
    # Check if settings already exist
    try:
        content = shell_rc.read_text()
        if "LANG=en_US.UTF-8" in content:
            print(f"✅ Locale settings already exist in {shell_rc}")
        else:
            print(f"📝 Adding locale settings to {shell_rc}...")
            settings = """

# RTL/Arabic support - Added by Arabic Restaurant Agent setup
export LANG=en_US.UTF-8
export LC_ALL=en_US.UTF-8
export TERM=xterm-256color
"""
            shell_rc.write_text(content + settings)
            print("✅ Added locale settings")
    except Exception as e:
        print(f"⚠️  Error updating {shell_rc}: {e}")
    
    # Check current locale
    print()
    print("Current locale settings:")
    try:
        result = subprocess.run(["locale"], capture_output=True, text=True)
        for line in result.stdout.split("\n"):
            if "LANG" in line or "LC_ALL" in line:
                print(f"  {line}")
    except Exception:
        print("⚠️  Could not check locale")
    
    # Check terminal type
    print()
    term = os.environ.get("TERM", "not set")
    print(f"Current terminal type: {term}")
    if term == "dumb":
        print("⚠️  Terminal type is 'dumb' - this may cause RTL issues")
        print("   Run: export TERM=xterm-256color")
    
    print()
    print("✅ Setup complete!")
    print()
    print("Next steps:")
    print(f"1. Restart iTerm2 or run: source {shell_rc}")
    print("2. Configure iTerm2: Preferences > Profiles > Text")
    print("   - Unicode normalization: NFC")
    print("   - Use Unicode version 9 widths: ✅")
    print("3. Test with: python3 scripts/test_rtl.py")
    print()
    print("See docs/ITERM2_RTL_SETUP.md for detailed instructions")

if __name__ == "__main__":
    main()

