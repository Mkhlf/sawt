#!/usr/bin/env python3
"""
Test RTL (Right-to-Left) text display in terminal.
Tests both standard RTL marks and fallback method.
"""
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.rtl import print_rtl as print_rtl_standard, wrap_rtl, contains_arabic
from core.rtl_fallback import print_rtl_fallback

print("=" * 60)
print("RTL Text Display Test")
print("=" * 60)
print()

print("METHOD 1: Standard RTL (Unicode bidirectional marks)")
print("-" * 60)
print("1. Arabic text (should display RTL):")
print_rtl_standard("مرحباً بك في مطعم البيت العربي! 🏠")
print()

print("2. Mixed Arabic and English:")
print_rtl_standard("Hello", "مرحباً", "World")
print()

print("3. Arabic with numbers:")
print_rtl_standard("السعر: 50 ريال")
print()

print("4. Long Arabic text:")
print_rtl_standard("عندنا عدة خيارات برجر: برجر كلاسيكي، برجر مشروم، برجر دجاج")
print()

print("5. English only (should display normally):")
print_rtl_standard("Hello World")
print()

print()
print("METHOD 2: Fallback (Reversed Arabic text)")
print("-" * 60)
print("1. Arabic text (reversed for display):")
print_rtl_fallback("مرحباً بك في مطعم البيت العربي! 🏠")
print()

print("2. Mixed Arabic and English:")
print_rtl_fallback("Hello", "مرحباً", "World")
print()

print("3. Arabic with numbers:")
print_rtl_fallback("السعر: 50 ريال")
print()

print("4. Long Arabic text:")
print_rtl_fallback("عندنا عدة خيارات برجر: برجر كلاسيكي، برجر مشروم، برجر دجاج")
print()

print("5. English only (should display normally):")
print_rtl_fallback("Hello World")
print()

print("=" * 60)
print("Test completed!")
print("=" * 60)
print()
print("Compare the two methods above:")
print("  - Method 1: Uses Unicode bidirectional marks (requires iTerm2 RTL support)")
print("  - Method 2: Reverses Arabic text (works in any terminal)")
print()
print("If Method 1 shows Arabic RIGHT-ALIGNED → ✅ RTL support works!")
print("If Method 1 shows Arabic LEFT-ALIGNED → Use Method 2 (fallback)")
print()
print("To use fallback in main.py, change:")
print("  from core.rtl import print_rtl")
print("  to:")
print("  from core.rtl_fallback import print_rtl_fallback as print_rtl")
