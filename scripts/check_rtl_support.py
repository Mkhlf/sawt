#!/usr/bin/env python3
"""
Check if terminal supports RTL (Right-to-Left) text properly.
"""
import sys
import os

def test_rtl_support():
    """Test if terminal renders RTL marks correctly."""
    print("=" * 60)
    print("RTL Support Check")
    print("=" * 60)
    print()
    
    # Test 1: Check locale
    print("1. Locale Check:")
    lang = os.environ.get("LANG", "Not set")
    lc_all = os.environ.get("LC_ALL", "Not set")
    print(f"   LANG: {lang}")
    print(f"   LC_ALL: {lc_all}")
    if "UTF-8" in str(lang) or "UTF-8" in str(lc_all):
        print("   ✅ Locale supports UTF-8")
    else:
        print("   ⚠️  Locale may not support UTF-8 properly")
    print()
    
    # Test 2: Check terminal type
    print("2. Terminal Type:")
    term = os.environ.get("TERM", "Not set")
    print(f"   TERM: {term}")
    if term == "dumb":
        print("   ⚠️  Terminal type is 'dumb' - RTL may not work")
    elif "xterm" in term or "iterm" in term.lower():
        print("   ✅ Terminal type should support RTL")
    else:
        print("   ⚠️  Unknown terminal type")
    print()
    
    # Test 3: Test Unicode bidirectional marks
    print("3. Unicode Bidirectional Marks Test:")
    test_text = "مرحباً"
    rtl_marked = "\u202B" + test_text + "\u202C"
    print(f"   Arabic text: {test_text}")
    print(f"   With RTL marks: {rtl_marked}")
    print()
    print("   👀 Look at the text above:")
    print("   - If Arabic appears RIGHT-ALIGNED → ✅ RTL works!")
    print("   - If Arabic appears LEFT-ALIGNED or reversed → ❌ RTL not working")
    print()
    
    # Test 4: Check Python encoding
    print("4. Python Encoding:")
    print(f"   stdout encoding: {sys.stdout.encoding}")
    print(f"   default encoding: {sys.getdefaultencoding()}")
    if sys.stdout.encoding and "utf" in sys.stdout.encoding.lower():
        print("   ✅ Python encoding supports UTF-8")
    else:
        print("   ⚠️  Python encoding may not support UTF-8")
    print()
    
    # Instructions
    print("=" * 60)
    print("iTerm2 Configuration:")
    print("=" * 60)
    print()
    print("If RTL is NOT working, enable experimental RTL support:")
    print("1. iTerm2 > Preferences (Cmd + ,)")
    print("2. Advanced > Experimental")
    print("3. ✅ Check 'Enable support for right-to-left scripts'")
    print("4. Restart iTerm2")
    print()
    print("Alternative: Use fallback method (reverses Arabic text):")
    print("  from core.rtl_fallback import print_rtl_fallback as print_rtl")
    print()

if __name__ == "__main__":
    test_rtl_support()

