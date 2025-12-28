"""
Menu agent tools: search_menu, get_item_details
"""
from agents import function_tool

# menu_engine will be set by main.py at startup
menu_engine = None


from functools import lru_cache
import time

# Cache invalidation timestamp (5 minute buckets)
_cache_timestamp = 0

def _get_cache_bucket():
    """Get current 5-minute cache bucket for invalidation."""
    return int(time.time() / 300)  # 300 seconds = 5 minutes

@lru_cache(maxsize=128)
def _search_menu_cached(query: str, cache_bucket: int) -> dict:
    """Cached menu search implementation."""
    if menu_engine is None:
        return {
            "found": False,
            "error": "menu_engine_not_initialized",
            "message": "نظام القائمة غير جاهز حالياً"
        }
    
    return menu_engine.search(query, top_k=5)

@function_tool
def search_menu(query: str) -> dict:
    """
    Search menu items using semantic similarity (with caching).
    
    Searches are cached for 5 minutes to reduce redundant API calls.
    
    Args:
        query: Arabic search query (e.g., "برجر كبير")
    
    Returns:
        {
            "found": bool,
            "count": int,
            "items": [
                {
                    "id": "main_001",
                    "name_ar": "برجر لحم كلاسيكي",
                    "name_en": "Classic Beef Burger",
                    "price": 35.0,
                    "category": "main_dishes",
                    "has_sizes": bool,
                    "score": 0.92
                },
                ...
            ]
        }
    """
    global _cache_timestamp
    
    current_bucket = _get_cache_bucket()
    
    # Invalidate cache if bucket changed (every 5 minutes)
    if current_bucket != _cache_timestamp:
        _search_menu_cached.cache_clear()
        _cache_timestamp = current_bucket
    
    return _search_menu_cached(query, current_bucket)


@function_tool
def get_item_details(item_id: str) -> dict:
    """
    Get full details for a specific menu item.
    
    Args:
        item_id: Menu item ID (e.g., "main_001")
    
    Returns:
        Full item details including sizes, customizations, description
    """
    if menu_engine is None:
        return {"found": False, "error": "menu_engine_not_initialized", "message": "نظام القائمة غير جاهز حالياً"}
    
    item = menu_engine.get_item_by_id(item_id)
    if not item:
        return {"found": False, "message": "الصنف غير موجود"}
    
    return {
        "found": True,
        "item": {
            "id": item["id"],
            "name_ar": item["name_ar"],
            "name_en": item.get("name_en", ""),
            "price": item["price"],
            "description_ar": item.get("description_ar", ""),
            "category": item["category"],
            "sizes": item.get("sizes", {}),
            "customizations": item.get("customizations", []),
            "available": item.get("available", True)
        }
    }

