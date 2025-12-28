"""
RTL (Right-to-Left) text handling utilities for Arabic terminal output.

iTerm2 Note: For best results, ensure iTerm2 is configured:
1. CRITICAL: Preferences > Advanced > Experimental > Enable support for right-to-left scripts
2. Preferences > Profiles > Text > Unicode normalization: NFC
3. Preferences > Profiles > Text > Use Unicode version 9 widths
4. Set locale: export LANG=en_US.UTF-8 in your shell config

If RTL still doesn't work after enabling experimental RTL support, try:
    from core.rtl_fallback import print_rtl_fallback as print_rtl
"""

import os
import re
import sys

# Unicode bidirectional marks
RTL_MARK = "\u202b"  # Right-to-Left Embedding
POP_MARK = "\u202c"  # Pop Directional Formatting
LTR_MARK = "\u202a"  # Left-to-Right Embedding

# Try to set UTF-8 locale if not already set
if not os.environ.get("LANG") or os.environ.get("LANG") == "C":
    # Try to set UTF-8 locale
    for lang in ["en_US.UTF-8", "en_GB.UTF-8", "C.UTF-8"]:
        try:
            import locale

            locale.setlocale(locale.LC_ALL, lang)
            os.environ["LANG"] = lang
            break
        except locale.Error:
            continue

# Ensure stdout uses UTF-8
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass


def contains_arabic(text: str) -> bool:
    """Check if text contains Arabic characters."""
    arabic_pattern = re.compile(
        r"[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]"
    )
    return bool(arabic_pattern.search(text))


def wrap_rtl(text: str) -> str:
    """
    Wrap Arabic text with Unicode bidirectional marks for proper terminal display.

    Args:
        text: Text that may contain Arabic characters

    Returns:
        Text wrapped with RTL marks if Arabic is detected
    """
    if not text:
        return text

    # If text contains Arabic, wrap it with RTL marks
    if contains_arabic(text):
        # Wrap entire text with RTL marks
        return f"{RTL_MARK}{text}{POP_MARK}"

    return text


def print_rtl(*args, **kwargs):
    """
    Print function that automatically handles RTL text.

    Usage:
        print_rtl("مرحباً")  # Automatically wraps with RTL marks
        print_rtl("Hello", "مرحباً")  # Mixed content handled
    """
    # Process all arguments
    processed_args = []
    for arg in args:
        if isinstance(arg, str):
            processed_args.append(wrap_rtl(arg))
        else:
            processed_args.append(str(arg))

    # Join if multiple args, otherwise use first
    if len(processed_args) > 1:
        output = " ".join(processed_args)
    elif processed_args:
        output = processed_args[0]
    else:
        output = ""

    print(output, **kwargs)
