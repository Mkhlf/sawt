"""
Order agent tools: add_to_order, get_current_order, remove_from_order, modify_order_item, select_from_offered
"""

import pyarabic.araby as araby
from agents import function_tool
from core.session import SessionStore, OrderItem

# menu_engine will be set by main.py at startup
menu_engine = None


def _normalize_for_comparison(text: str) -> str:
    """Normalize Arabic text for name comparison."""
    if not text:
        return ""
    text = araby.strip_tashkeel(text)
    text = araby.normalize_alef(text)
    text = araby.normalize_hamza(text)
    text = araby.normalize_teh(text)
    return text.lower().strip()


@function_tool
def add_to_order(
    item_id: str, 
    quantity: int = 1, 
    size: str = None, 
    notes: str = ""
) -> dict:
    """
    Add item to current order.

    Args:
        item_id: Menu item ID from search_menu result (e.g., "main_016")
        quantity: Number of items (default: 1)
        size: Size option if applicable (e.g., "صغير", "وسط", "كبير")
        notes: Special instructions (e.g., "بدون بصل")

    Returns:
        {
            "success": bool,
            "item_added": {...},
            "current_total": float,
            "message": str
        }
    """
    if menu_engine is None:
        return {
            "success": False,
            "error": "menu_engine_not_initialized",
            "message": "نظام القائمة غير جاهز حالياً",
        }

    # Get item details by ID
    item = menu_engine.get_item_by_id(item_id)

    # If not found by ID, try searching by name (more robust)
    if not item:
        search_result = menu_engine.search(item_id, top_k=1)
        if search_result.get("found") and search_result.get("items"):
            best_match = search_result["items"][0]
            if best_match.get("score", 0) >= 0.7:
                item = menu_engine.get_item_by_id(best_match["id"])
                item_id = best_match["id"]

    if not item:
        return {
            "success": False,
            "error": "item_not_found",
            "message": "الصنف غير موجود",
        }

    if not item.get("available", True):
        return {
            "success": False,
            "error": "item_unavailable",
            "message": f"عذراً، {item['name_ar']} غير متوفر حالياً",
        }

    if quantity < 1 or quantity > 10:
        return {
            "success": False,
            "error": "invalid_quantity",
            "message": "الكمية لازم تكون بين ١ و ١٠",
        }

    # Handle size pricing - ensure price is always a number
    base_price = item.get("price", 0)

    # If price is a dict (sizes), get the specified size or default
    if isinstance(base_price, dict):
        if size and size in base_price:
            base_price = base_price[size]
        elif "وسط" in base_price:
            base_price = base_price["وسط"]  # Default to medium
        elif base_price:
            base_price = list(base_price.values())[0]  # Fallback to first size
        else:
            base_price = 0
    elif size:
        # Size specified but item doesn't have size options
        return {
            "success": False,
            "error": "invalid_size",
            "message": f"هذا الصنف لا يحتوي على أحجام. الحجم '{size}' غير متوفر.",
        }

    # Final validation - ensure base_price is a number
    if not isinstance(base_price, (int, float)):
        return {
            "success": False,
            "error": "invalid_price",
            "message": f"خطأ في سعر الصنف",
        }

    # Add to session order
    session = SessionStore.get_current()
    order_item = OrderItem(
        item_id=item_id,
        name_ar=item["name_ar"],
        quantity=quantity,
        unit_price=base_price,
        size=size,
        notes=notes,
    )
    session.order_items.append(order_item)

    # Clear pending order text since we've processed the order
    session.pending_order_items.clear()  # Clear list instead of setting to None

    size_text = f" ({size})" if size else ""
    return {
        "success": True,
        "item_added": {
            "index": len(session.order_items),  # 1-based for user reference
            "name_ar": item["name_ar"],
            "size": size,
            "quantity": quantity,
            "unit_price": base_price,
            "total_price": order_item.total_price,
            "notes": notes,
        },
        "current_total": session.subtotal,
        "message": f"تم إضافة {quantity} {item['name_ar']}{size_text} للطلب ✓",
    }


@function_tool
def get_current_order() -> dict:
    """
    Get current order summary.

    Returns:
        {
            "items": [...],
            "subtotal": float,
            "item_count": int,
            "formatted_summary": str  # Arabic formatted
        }
    """
    session = SessionStore.get_current()

    if not session.order_items:
        return {
            "items": [],
            "subtotal": 0,
            "item_count": 0,
            "formatted_summary": "الطلب فاضي",
        }

    formatted_lines = []
    for idx, item in enumerate(session.order_items, start=1):
        size_text = f" {item.size}" if item.size else ""
        line = f"{idx}. {item.quantity} {item.name_ar}{size_text} - {item.total_price} ريال"
        if item.notes:
            line += f" ({item.notes})"
        formatted_lines.append(line)

    formatted = "\n".join(formatted_lines)
    formatted += f"\n\nالمجموع: {session.subtotal} ريال"

    return {
        "items": [
            {
                "index": idx,
                "item_id": item.item_id,
                "name_ar": item.name_ar,
                "quantity": item.quantity,
                "size": item.size,
                "unit_price": item.unit_price,
                "total_price": item.total_price,
                "notes": item.notes,
            }
            for idx, item in enumerate(session.order_items, start=1)
        ],
        "subtotal": session.subtotal,
        "item_count": sum(item.quantity for item in session.order_items),
        "formatted_summary": formatted,
    }


@function_tool
def remove_from_order(item_name: str = None, item_index: int = None) -> dict:
    """
    Remove item from current order by NAME or index.

    ⚠️ PREFERRED: Use item_name for reliable matching!

    Args:
        item_name: Name/partial name of item to remove (e.g., "كرك", "برجر") - PREFERRED!
        item_index: 1-based index (fallback, use only if name doesn't work)

    Returns:
        {
            "success": bool,
            "removed_item": {...},
            "current_total": float,
            "message": str
        }
    """
    session = SessionStore.get_current()

    if not session.order_items:
        return {"success": False, "error": "empty_order", "message": "الطلب فاضي"}

    idx = None

    # PREFERRED: Find by item name
    if item_name:
        search_name = item_name.strip().lower()
        for i, order_item in enumerate(session.order_items):
            item_name_lower = order_item.name_ar.lower()
            if search_name in item_name_lower or item_name_lower in search_name:
                idx = i
                break

        # Partial match fallback
        if idx is None:
            for i, order_item in enumerate(session.order_items):
                item_words = order_item.name_ar.lower().split()
                if any(
                    search_name in word or word in search_name for word in item_words
                ):
                    idx = i
                    break

        if idx is None:
            items_list = [
                f"{i+1}. {item.name_ar}" for i, item in enumerate(session.order_items)
            ]
            return {
                "success": False,
                "error": "item_not_found_in_order",
                "message": f"⚠️ ما لقيت '{item_name}' في طلبك. الأصناف الموجودة:\n"
                + "\n".join(items_list),
            }

    # Fallback: Use index
    elif item_index is not None:
        idx = item_index - 1
        if idx < 0 or idx >= len(session.order_items):
            return {
                "success": False,
                "error": "invalid_index",
                "message": f"رقم الصنف غير صحيح. الطلب فيه {len(session.order_items)} أصناف",
            }
    else:
        return {
            "success": False,
            "error": "no_item_specified",
            "message": "⚠️ حدد الصنف اللي تبي تحذفه (الاسم أو الرقم)",
        }

    # Remove the item
    removed = session.order_items.pop(idx)

    return {
        "success": True,
        "removed_item": {
            "name_ar": removed.name_ar,
            "quantity": removed.quantity,
            "total_price": removed.total_price,
        },
        "current_total": session.subtotal,
        "remaining_items": len(session.order_items),
        "message": f"تم حذف {removed.name_ar} من الطلب ✓",
    }


@function_tool
def modify_order_item(
    item_name: str = None,
    item_index: int = None,
    quantity: int = None,
    size: str = None,
    notes: str = None,
) -> dict:
    """
    Modify an existing item in the order by NAME or index.

    ⚠️ PREFERRED: Use item_name for reliable matching!
    When user says "خلي الكرك ٤" → use item_name="شاي كرك" or item_name="كرك"

    Args:
        item_name: Name/partial name of item to modify (e.g., "كرك", "برجر لحم") - PREFERRED!
        item_index: 1-based index (fallback, use only if name doesn't work)
        quantity: New quantity (optional, keeps current if not provided)
        size: New size (optional, keeps current if not provided)
        notes: New special instructions (optional, keeps current if not provided)

    Returns:
        {
            "success": bool,
            "modified_item": {...},
            "current_total": float,
            "message": str
        }
    """
    if menu_engine is None:
        return {
            "success": False,
            "error": "menu_engine_not_initialized",
            "message": "نظام القائمة غير جاهز حالياً",
        }

    session = SessionStore.get_current()

    if not session.order_items:
        return {"success": False, "error": "empty_order", "message": "الطلب فاضي"}

    idx = None

    # PREFERRED: Find by item name
    if item_name:
        search_name = item_name.strip().lower()
        for i, order_item in enumerate(session.order_items):
            item_name_lower = order_item.name_ar.lower()
            # Match if search term is in item name or item name contains search term
            if search_name in item_name_lower or item_name_lower in search_name:
                idx = i
                break

        # If not found by direct match, try partial match
        if idx is None:
            for i, order_item in enumerate(session.order_items):
                # Check each word
                item_words = order_item.name_ar.lower().split()
                if any(
                    search_name in word or word in search_name for word in item_words
                ):
                    idx = i
                    break

        if idx is None:
            # List available items for user
            items_list = [
                f"{i+1}. {item.name_ar}" for i, item in enumerate(session.order_items)
            ]
            return {
                "success": False,
                "error": "item_not_found_in_order",
                "message": f"⚠️ ما لقيت '{item_name}' في طلبك. الأصناف الموجودة:\n"
                + "\n".join(items_list),
            }

    # Fallback: Use index if provided and name didn't find anything
    elif item_index is not None:
        idx = item_index - 1  # Convert to 0-based
        if idx < 0 or idx >= len(session.order_items):
            return {
                "success": False,
                "error": "invalid_index",
                "message": f"رقم الصنف غير صحيح. الطلب فيه {len(session.order_items)} أصناف",
            }
    else:
        return {
            "success": False,
            "error": "no_item_specified",
            "message": "⚠️ حدد الصنف اللي تبي تعدله (الاسم أو الرقم)",
        }

    item = session.order_items[idx]
    changes = []

    # Update quantity if provided
    if quantity is not None:
        if quantity < 1 or quantity > 10:
            return {
                "success": False,
                "error": "invalid_quantity",
                "message": "الكمية لازم تكون بين ١ و ١٠",
            }
        old_qty = item.quantity
        item.quantity = quantity
        changes.append(f"الكمية: {old_qty} → {quantity}")

    # Update size if provided
    if size is not None:
        # Get item from menu to validate size and get new price
        menu_item = menu_engine.get_item_by_id(item.item_id)
        price_data = menu_item.get("price", {}) if menu_item else {}

        # Check if item has size options (price is a dict)
        if menu_item and isinstance(price_data, dict) and size in price_data:
            item.size = size
            item.unit_price = price_data[size]
            changes.append(f"الحجم: {size}")
        elif size:
            return {
                "success": False,
                "error": "invalid_size",
                "message": f"الحجم '{size}' غير متوفر لهذا الصنف",
            }

    # Update notes if provided
    if notes is not None:
        item.notes = notes
        changes.append(f"الملاحظات: {notes or 'بدون'}")

    if not changes:
        return {
            "success": False,
            "error": "no_changes",
            "message": "لم يتم تحديد أي تعديلات",
        }

    return {
        "success": True,
        "modified_item": {
            "index": item_index,
            "name_ar": item.name_ar,
            "quantity": item.quantity,
            "size": item.size,
            "unit_price": item.unit_price,
            "total_price": item.total_price,
            "notes": item.notes,
        },
        "changes": changes,
        "current_total": session.subtotal,
        "message": f"تم تعديل {item.name_ar}: {', '.join(changes)} ✓",
    }


@function_tool
def store_offered_items(items_json: str) -> dict:
    """
    Store items that were just offered to the user for later selection.
    Call this AFTER search_menu when you show multiple options to user.
    
    Args:
        items_json: JSON string of items from search_menu result
                   Example: '[{"id": "main_016", "name_ar": "برجر لحم", "price": 47}]'
        
    Returns:
        {"success": true, "stored_count": N}
    """
    import json
    
    session = SessionStore.get_current()
    
    # Parse JSON string
    try:
        items = json.loads(items_json) if isinstance(items_json, str) else items_json
    except (json.JSONDecodeError, TypeError):
        return {
            "success": False,
            "error": "invalid_json",
            "message": "⚠️ صيغة الخيارات غير صحيحة",
        }
    
    # Store in session for later reference
    if not hasattr(session, 'last_offered_items'):
        session.last_offered_items = []
    
    session.last_offered_items = items[:5] if isinstance(items, list) else []
    
    return {
        "success": True,
        "stored_count": len(session.last_offered_items),
        "message": f"تم حفظ {len(session.last_offered_items)} خيارات",
    }


@function_tool
def select_from_offered(selection_hint: str, quantity: int = 1) -> dict:
    """
    Select an item from previously offered options.
    Use this when user says a partial match like "مشوي" or "دجاج" after you showed options.
    
    ⚠️ IMPORTANT: Use this instead of search_menu when user is selecting from YOUR offered options!
    
    Args:
        selection_hint: What user said to select (e.g., "مشوي", "الثاني", "دجاج")
        quantity: How many to add (default: 1)
        
    Returns:
        If matched: {"matched": true, "item": {...}, "added": true}
        If not matched: {"matched": false, "hint": "...", "offered": [...]}
    """
    session = SessionStore.get_current()
    
    if not hasattr(session, 'last_offered_items') or not session.last_offered_items:
        return {
            "matched": False,
            "error": "no_offers",
            "message": "⚠️ لا يوجد خيارات محفوظة. استخدم search_menu بدلاً.",
        }
    
    hint = _normalize_for_comparison(selection_hint)
    
    # Try to match hint to offered items
    for item in session.last_offered_items:
        item_name = _normalize_for_comparison(item.get("name_ar", ""))
        
        # Check if hint matches item name
        if hint in item_name or item_name in hint:
            # Found a match! Add it to order
            item_id = item.get("id")
            if item_id and menu_engine:
                full_item = menu_engine.get_item_by_id(item_id)
                if full_item:
                    # Get price from full item (menu data is the source of truth)
                    price = full_item.get("price", 0)
                    if isinstance(price, dict):
                        # Has sizes - use medium as default
                        price = price.get("وسط", price.get("medium", list(price.values())[0] if price else 0))
                    
                    # Add to order
                    order_item = OrderItem(
                        item_id=item_id,
                        name_ar=full_item["name_ar"],
                        quantity=quantity,
                        unit_price=price if isinstance(price, (int, float)) else 0,
                    )
                    session.order_items.append(order_item)
                    
                    # Clear offered items after selection
                    session.last_offered_items = []
                    
                    return {
                        "matched": True,
                        "item": {
                            "id": item_id,
                            "name_ar": full_item["name_ar"],
                            "price": price,
                        },
                        "added": True,
                        "quantity": quantity,
                        "current_total": session.subtotal,
                        "message": f"تم إضافة {quantity} {full_item['name_ar']} للطلب ✓",
                    }
    
    # No match found
    return {
        "matched": False,
        "hint": selection_hint,
        "offered": session.last_offered_items,
        "message": f"⚠️ '{selection_hint}' غير موجود في الخيارات المعروضة. اطلب من العميل التوضيح.",
    }
