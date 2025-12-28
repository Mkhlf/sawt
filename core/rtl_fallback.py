"""
Fallback RTL solution for iTerm2 when experimental RTL support is disabled.

This module provides an alternative approach that reverses Arabic text
for display when Unicode bidirectional marks don't work.
"""
import re
from .rtl import contains_arabic


def reverse_arabic_segments(text: str) -> str:
    """
    Reverse Arabic segments in text for display when RTL marks don't work.
    
    This is a workaround for terminals that don't support Unicode bidirectional marks.
    When Arabic text is displayed left-to-right without RTL support, it appears backwards.
    Reversing the entire Arabic string makes it readable.
    
    Args:
        text: Text that may contain Arabic characters
        
    Returns:
        Text with Arabic segments reversed as whole strings
    """
    if not text:
        return text
    
    if not contains_arabic(text):
        return text
    
    # Use regex to find Arabic character sequences (preserve numbers and most punctuation)
    import re
    # Match only Arabic characters, Arabic punctuation, and spaces between Arabic chars
    arabic_char_pattern = re.compile(
        r"[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]"
    )
    arabic_punct_pattern = re.compile(r"[،؛؟]")
    
    # Find contiguous Arabic segments (Arabic chars + Arabic punctuation + spaces between them)
    parts = []
    i = 0
    
    while i < len(text):
        if arabic_char_pattern.match(text[i]):
            # Found start of Arabic segment - collect until non-Arabic
            arabic_segment = ""
            while i < len(text) and (
                arabic_char_pattern.match(text[i])
                or arabic_punct_pattern.match(text[i])
                or (text[i].isspace() and i + 1 < len(text) and arabic_char_pattern.match(text[i + 1]))
            ):
                arabic_segment += text[i]
                i += 1
            
            # Reverse the Arabic segment
            parts.append(arabic_segment[::-1])
        else:
            # Non-Arabic character - keep as is
            parts.append(text[i])
            i += 1
    
    return "".join(parts)


def print_rtl_fallback(*args, **kwargs):
    """
    Print RTL text using fallback method (reverses Arabic text).
    
    Use this if Unicode bidirectional marks don't work in your terminal.
    """
    processed_args = []
    for arg in args:
        if isinstance(arg, str):
            processed_args.append(reverse_arabic_segments(arg))
        else:
            processed_args.append(str(arg))
    
    if len(processed_args) > 1:
        output = " ".join(processed_args)
    elif processed_args:
        output = processed_args[0]
    else:
        output = ""
    
    print(output, **kwargs)

