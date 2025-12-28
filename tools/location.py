"""
Location agent tools: check_delivery_district
"""
from agents import function_tool
import json
import pyarabic.araby as araby
from pathlib import Path

# Cache for coverage zones
_coverage_zones_cache = None


def _load_coverage_zones() -> dict:
    """
    Load coverage zones from data/coverage_zones.json.
    Cached after first load.
    """
    global _coverage_zones_cache
    if _coverage_zones_cache is None:
        zones_path = Path(__file__).parent.parent / "data" / "coverage_zones.json"
        with open(zones_path, "r", encoding="utf-8") as f:
            _coverage_zones_cache = json.load(f)
    return _coverage_zones_cache


def _normalize_district_name(district: str) -> str:
    """
    Normalize Arabic district name for consistent matching.
    
    Handles:
    - Diacritics removal (tashkeel)
    - Alef normalization (أ إ آ → ا)
    - Common prefixes: "حي ", "حيّ ", "منطقة "
    - Extra whitespace
    """
    # Strip diacritics and normalize alef
    text = araby.strip_tashkeel(district)
    text = araby.normalize_alef(text)
    text = araby.normalize_hamza(text)
    
    # Remove common prefixes
    prefixes = ["حي ", "حى ", "منطقة ", "شارع "]
    for prefix in prefixes:
        if text.startswith(prefix):
            text = text[len(prefix):]
            break
    
    # Normalize whitespace
    text = " ".join(text.split())
    
    return text.strip()


def _levenshtein_distance(s1: str, s2: str) -> int:
    """Simple Levenshtein distance for typo tolerance."""
    if len(s1) < len(s2):
        return _levenshtein_distance(s2, s1)
    if len(s2) == 0:
        return len(s1)
    
    prev_row = range(len(s2) + 1)
    for i, c1 in enumerate(s1):
        curr_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = prev_row[j + 1] + 1
            deletions = curr_row[j] + 1
            substitutions = prev_row[j] + (c1 != c2)
            curr_row.append(min(insertions, deletions, substitutions))
        prev_row = curr_row
    
    return prev_row[-1]


def _find_matching_district(normalized: str, coverage_zones: dict) -> str | None:
    """
    Find matching district with STRICT matching.
    
    Matching priority:
    1. Exact match after normalization
    2. Substring match ONLY if the match is very close (>80% of characters)
    
    NOTE: Removed loose fuzzy matching because it was matching
    "الدمام" to "الرمال" (edit distance 2) which is wrong!
    """
    # Normalize all zone names for comparison
    zone_names = list(coverage_zones.keys())
    normalized_zones = {_normalize_district_name(z): z for z in zone_names}
    
    # 1. Exact match
    if normalized in normalized_zones:
        return normalized_zones[normalized]
    
    # 2. Strict substring match - only if one contains the other AND they're very similar
    for norm_zone, orig_zone in normalized_zones.items():
        # One must contain the other
        if norm_zone in normalized or normalized in norm_zone:
            # AND the shorter must be at least 80% of the longer
            shorter = min(len(norm_zone), len(normalized))
            longer = max(len(norm_zone), len(normalized))
            if shorter >= longer * 0.8:
                return orig_zone
    
    # 3. Very strict edit distance - only for single character typos
    # Use relative threshold: max 1 edit per 5 characters
    for norm_zone, orig_zone in normalized_zones.items():
        max_edits = max(1, len(norm_zone) // 5)  # 1 edit for short words
        if _levenshtein_distance(normalized, norm_zone) <= max_edits:
            return orig_zone
    
    return None


@function_tool
def check_delivery_district(district: str) -> dict:
    """
    Check if district is within delivery coverage.
    
    Args:
        district: District/neighborhood name in Arabic
    
    Returns:
        {
            "covered": bool,
            "district": str,           # Normalized district name
            "delivery_fee": float,     # In SAR (0 if not covered)
            "estimated_time": str,     # Arabic time estimate
            "message": str             # Arabic response message
        }
    
    Error Returns:
        {
            "covered": False,
            "error": "district_not_found" | "service_unavailable",
            "message": str,
            "suggestions": list[str]   # Nearby covered districts
        }
    """
    from core.session import SessionStore
    
    # Load coverage zones from data file
    coverage_zones = _load_coverage_zones()
    
    # Normalize input for matching
    normalized = _normalize_district_name(district)
    
    # Find matching district with fuzzy matching
    matched_district = _find_matching_district(normalized, coverage_zones)
    
    if matched_district:
        zone = coverage_zones[matched_district]
        
        # Update session with location info
        try:
            session = SessionStore.get_current()
            session.district = matched_district
            session.delivery_fee = zone["fee"]
            session.estimated_time = zone["time"]
            session.order_mode = "delivery"
            session.intent = "delivery"
            session.location_confirmed = True  # Mark location as confirmed!
        except RuntimeError:
            pass  # No session yet
        
        return {
            "covered": True,
            "district": matched_district,
            "delivery_fee": zone["fee"],
            "estimated_time": zone["time"],
            "message": f"تمام! التوصيل لـ{matched_district} متاح. الرسوم: {zone['fee']} ريال، الوقت: {zone['time']}"
        }
    
    # Not covered - suggest some available districts
    suggestions = list(coverage_zones.keys())[:4]  # First 4 covered districts
    return {
        "covered": False,
        "rejected": True,  # Make it very explicit
        "district": district,
        "delivery_fee": 0,
        "estimated_time": None,
        "error": "district_not_found",
        "message": f"⚠️ عذراً! حي {district} خارج نطاق التوصيل!",
        "action_required": "اطلب حي آخر من العميل أو اقترح الاستلام",
        "suggestions": suggestions,
        "pickup_available": True,
        "DO_NOT_SAVE_THIS_ADDRESS": True  # Explicit instruction for the model
    }

