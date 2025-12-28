"""
Universal session tools - can be used by any agent to capture user info.
These tools allow agents to store information whenever the user provides it.
"""

from agents import function_tool
from core.session import SessionStore


@function_tool
def set_order_mode(mode: str) -> dict:
    """
    Set the order mode (delivery or pickup).
    Call this when user indicates they want delivery or pickup.

    ⚠️ IMPORTANT: This does NOT change the order items!
    Order items are preserved when switching modes.

    ⚠️ IDEMPOTENCY: If mode is already set to the SAME value, returns early.
    ✅ OVERRIDES ALLOWED: If user wants to CHANGE the mode (e.g., "خليه استلام" when currently delivery), call this to update!
    Check SESSION_STATE first - only skip if the value is already set AND user hasn't indicated a change!

    Args:
        mode: "delivery" or "pickup"

    Returns:
        {"success": bool, "mode": str, "message": str, "order_preserved": bool, "already_set": bool}
    """
    session = SessionStore.get_current()

    if mode not in ["delivery", "pickup"]:
        return {
            "success": False,
            "error": "invalid_mode",
            "message": "النوع لازم يكون 'delivery' أو 'pickup'",
        }

    # IDEMPOTENCY CHECK: If already set to the same mode, return early
    if session.order_mode == mode:
        mode_ar = "توصيل" if mode == "delivery" else "استلام من الفرع"
        return {
            "success": True,
            "mode": mode,
            "already_set": True,
            "message": f"⚠️ نوع الطلب '{mode_ar}' محفوظ مسبقاً! لا حاجة لإعادة الحفظ.",
            "order_items_preserved": len(session.order_items),
        }

    old_mode = session.order_mode
    session.order_mode = mode
    session.intent = mode

    # If switching to pickup, clear delivery-specific fields
    if mode == "pickup":
        session.delivery_fee = 0
        session.location_confirmed = False
        # Keep district in case they switch back, but don't use it

    mode_ar = "توصيل" if mode == "delivery" else "استلام من الفرع"
    items_count = len(session.order_items)

    return {
        "success": True,
        "mode": mode,
        "previous_mode": old_mode,
        "already_set": False,
        "order_items_preserved": items_count,
        "delivery_fee": session.delivery_fee,
        "message": f"تم تغيير نوع الطلب إلى: {mode_ar}. الطلب ({items_count} أصناف) محفوظ ✓",
    }


@function_tool
def set_customer_name(name: str) -> dict:
    """
    Store customer's name.
    Call this whenever the user mentions their name.

    ⚠️ IDEMPOTENCY: If name is already set to the SAME value, returns early.
    ✅ OVERRIDES ALLOWED: If user wants to CHANGE their name (e.g., "لا، اسمي أحمد" when currently "محمد"), call this to update!
    Check SESSION_STATE first - only skip if the value is already set AND user hasn't indicated a change!

    Args:
        name: Customer's name

    Returns:
        {"success": bool, "name": str, "already_set": bool}
    """
    session = SessionStore.get_current()

    # IDEMPOTENCY CHECK: If already set to the same name, return early
    if session.customer_name and session.customer_name.strip() == name.strip():
        return {
            "success": True,
            "name": name,
            "already_set": True,
            "message": f"⚠️ الاسم '{name}' محفوظ مسبقاً! لا حاجة لإعادة الحفظ.",
        }

    session.customer_name = name
    return {
        "success": True,
        "name": name,
        "already_set": False,
        "message": f"تم حفظ الاسم: {name}",
    }


@function_tool
def set_phone_number(phone: str) -> dict:
    """
    Store customer's phone number.
    Call this whenever the user provides their phone number.

    ⚠️ IDEMPOTENCY: If phone is already set to the SAME value, returns early.
    ✅ OVERRIDES ALLOWED: If user wants to CHANGE their phone (e.g., "لا، رقمي 0561234567" when currently different), call this to update!
    Check SESSION_STATE first - only skip if the value is already set AND user hasn't indicated a change!

    Args:
        phone: Phone number (any format)

    Returns:
        {"success": bool, "phone": str, "already_set": bool}
    """
    session = SessionStore.get_current()

    # Normalize phone for comparison (remove spaces, dashes, etc.)
    normalized_phone = phone.strip().replace(" ", "").replace("-", "").replace("_", "")
    existing_phone = (
        (session.phone_number or "")
        .strip()
        .replace(" ", "")
        .replace("-", "")
        .replace("_", "")
    )

    # IDEMPOTENCY CHECK: If already set to the same phone, return early
    if existing_phone and normalized_phone == existing_phone:
        return {
            "success": True,
            "phone": phone,
            "already_set": True,
            "message": f"⚠️ رقم الجوال '{phone}' محفوظ مسبقاً! لا حاجة لإعادة الحفظ.",
        }

    session.phone_number = phone
    return {
        "success": True,
        "phone": phone,
        "already_set": False,
        "message": f"تم حفظ رقم الجوال: {phone}",
    }


@function_tool
def set_delivery_address(
    street_name: str = None, building_number: str = None, additional_info: str = None
) -> dict:
    """
    Store structured delivery address details.

    ⚠️ IMPORTANT: Only use AFTER check_delivery_district() confirms the district!

    Args:
        street_name: Street name (e.g., "شارع الأمير محمد") - REQUIRED
        building_number: Building/villa number (e.g., "23", "فيلا 5") - REQUIRED
        additional_info: Additional directions (e.g., "الدور الثاني", "بجانب المسجد") - OPTIONAL

    Returns:
        {"success": bool, "full_address": str, "missing_fields": list}
    """
    session = SessionStore.get_current()

    # Check if location was confirmed first
    if not session.location_confirmed:
        return {
            "success": False,
            "error": "district_not_confirmed",
            "message": "⚠️ يجب التحقق من الحي أولاً باستخدام check_delivery_district()",
        }

    # Track what was provided
    if street_name:
        session.street_name = street_name.strip()
    if building_number:
        session.building_number = building_number.strip()
    if additional_info:
        session.additional_info = additional_info.strip()

    # Check what's still missing
    missing = []
    if not session.street_name:
        missing.append("اسم الشارع")
    if not session.building_number:
        missing.append("رقم المبنى/الفيلا")

    if missing:
        session.address_complete = False
        return {
            "success": True,
            "partial": True,
            "district": session.district,
            "street_name": session.street_name,
            "building_number": session.building_number,
            "missing_fields": missing,
            "message": f"⚠️ العنوان غير مكتمل. ناقص: {', '.join(missing)}",
        }

    # Address is complete
    session.address_complete = True
    session.full_address = session.build_full_address()
    session.address_confirmed = True

    return {
        "success": True,
        "complete": True,
        "district": session.district,
        "street_name": session.street_name,
        "building_number": session.building_number,
        "additional_info": session.additional_info,
        "full_address": session.full_address,
        "message": f"✅ العنوان مكتمل: {session.full_address}",
    }


@function_tool
def add_pending_item(text: str, quantity: int = 1) -> dict:
    """
    Add a single item to the pending orders list.
    Use this when user mentions items before we can process them (e.g., during greeting).
    
    **NEW STRUCTURED API** - Replaces append_pending_order and set_pending_order
    
    Items are stored as a list with metadata:
    - text: What the user said (e.g., "برجر", "بيتزا كبيرة")
    - quantity: How many (default 1)
    - processed: False initially, set to True after Order Agent processes
    
    **Example Usage:**
    User: "أبي برجر"
      → add_pending_item(text="برجر", quantity=1)
    
    User: "وثنتين بيتزا"
      → add_pending_item(text="بيتزا", quantity=2)
    
    Result: pending_order_items = [
        {"text": "برجر", "quantity": 1, "processed": False},
        {"text": "بيتزا", "quantity": 2, "processed": False}
    ]
    
    Args:
        text: Item text (e.g., "برجر دجاج", "شاورما لحم")
        quantity: Number of items (default 1)
        
    Returns:
        {
            "success": bool,
            "item": dict,
            "total_pending": int,
            "message": str
        }
    """
    session = SessionStore.get_current()
    
    # Create item dict
    item = {
        "text": text.strip(),
        "quantity": quantity,
        "processed": False
    }
    
    # Add to list
    session.pending_order_items.append(item)
    
    return {
        "success": True,
        "item": item,
        "total_pending": len(session.pending_order_items),
        "message": f"تم إضافة '{text}' (العدد: {quantity}) للطلب المعلق. المجموع: {len(session.pending_order_items)} عنصر",
    }


@function_tool
def get_pending_items() -> dict:
    """
    Get all unprocessed pending items.
    Use this in Order Agent to see what needs to be processed.
    
    Returns ONLY items where processed=False.
    
    Returns:
        {
            "items": list,  # List of unprocessed items
            "count": int,   # Number of unprocessed items
            "message": str
        }
    """
    session = SessionStore.get_current()
    
    # Filter for unprocessed items only
    unprocessed = [item for item in session.pending_order_items if not item.get("processed", False)]
    
    if not unprocessed:
        return {
            "items": [],
            "count": 0,
            "message": "لا توجد عناصر معلقة للمعالجة"
        }
    
    return {
        "items": unprocessed,
        "count": len(unprocessed),
        "message": f"يوجد {len(unprocessed)} عنصر معلق يحتاج معالجة"
    }


@function_tool
def mark_pending_item_processed(index: int) -> dict:
    """
    Mark a pending item as processed.
    Call this after successfully processing an item.
    
    Args:
        index: Index in pending_order_items list (0-based)
        
    Returns:
        {"success": bool, "item": dict, "message": str}
    """
    session = SessionStore.get_current()
    
    if index < 0 or index >= len(session.pending_order_items):
        return {
            "success": False,
            "error": "invalid_index",
            "message": f"❌ الفهرس {index} غير صالح"
        }
    
    session.pending_order_items[index]["processed"] = True
    item = session.pending_order_items[index]
    
    return {
        "success": True,
        "item": item,
        "message": f"✓ تم وضع علامة '{item['text']}' كمعالج"
    }


@function_tool
def clear_pending_orders() -> dict:
    """
    Clear ALL pending order items.
    
    **IMPORTANT: Call this BEFORE transferring from Order Agent!**
    This prevents pending items from being re-processed on next Order Agent turn.
    
    Typical flow:
    1. Order Agent processes all pending items
    2. Adds them to actual order
    3. Calls clear_pending_orders()
    4. Transfers to next agent
    
    Returns:
        {"success": bool, "cleared_count": int, "message": str}
    """
    session = SessionStore.get_current()
    
    count = len(session.pending_order_items)
    session.pending_order_items = []
    
    return {
        "success": True,
        "cleared_count": count,
        "message": f"✓ تم مسح {count} عنصر معلق" if count > 0 else "لا توجد عناصر معلقة"
    }


# DEPRECATED TOOLS - Kept for backward compatibility
@function_tool
def set_pending_order(order_text: str) -> dict:
    """
    **⚠️ DEPRECATED: Use `add_pending_item` instead!**
    
    This function converts string to single item and adds to list.
    
    Args:
        order_text: What the user wants to order
    
    Returns:
        {"success": bool, "deprecated_warning": str}
    """
    # Convert to new format
    result = add_pending_item(text=order_text, quantity=1)
    result["deprecated_warning"] = "⚠️ set_pending_order is deprecated. Use add_pending_item instead!"
    return result


@function_tool
def append_pending_order(text: str) -> dict:
    """
    **⚠️ DEPRECATED: Use `add_pending_item` instead!**
    
    This function is kept for backward compatibility.
    
    Args:
        text: Order text to append
        
    Returns:
        {"success": bool, "deprecated_warning": str}
    """
    # Redirect to new API
    result = add_pending_item(text=text, quantity=1)
    result["deprecated_warning"] = "⚠️ append_pending_order is deprecated. Use add_pending_item instead!"
    return result


@function_tool
def get_session_state() -> dict:
    """
    Get current session state.
    Use this to check what information has already been collected.

    Returns:
        Full session state including name, phone, order mode, items, etc.
    """
    session = SessionStore.get_current()

    return {
        "customer_name": session.customer_name,
        "phone_number": session.phone_number,
        "order_mode": session.order_mode,
        "intent": session.intent,
        "district": session.district,
        "full_address": session.full_address,
        "location_confirmed": session.location_confirmed,
        "delivery_fee": session.delivery_fee,
        "estimated_time": session.estimated_time,
        "pending_order": ", ".join(item.get("text", "") for item in session.pending_order_items) if session.pending_order_items else None,
        "order_items_count": len(session.order_items),
        "subtotal": session.subtotal,
        "constraints": session.constraints,
    }


@function_tool
def get_order_summary() -> dict:
    """
    Get summary of order state for routing decisions.
    Use this to decide which agent to transfer to next.
    
    **Use Case:** Location Agent uses this to decide:
    - If order empty OR has pending items → transfer_to_order
    - Else → transfer_to_checkout
    
    Returns:
        {
            "items_count": int,
            "has_pending": bool,
            "pending_count": int,  # NEW: Count of unprocessed pending items
            "mode": str,
            "location_confirmed": bool,
            "address_complete": bool
        }
    """
    session = SessionStore.get_current()
    
    # Count unprocessed pending items
    unprocessed_pending = [item for item in session.pending_order_items if not item.get("processed", False)]
    
    return {
        "items_count": len(session.order_items),
        "has_pending": len(unprocessed_pending) > 0,
        "pending_count": len(unprocessed_pending),
        "mode": session.order_mode,
        "location_confirmed": session.location_confirmed,
        "address_complete": session.address_complete if hasattr(session, 'address_complete') else False,
    }


@function_tool
def defer_question(question: str, category: str = "order") -> dict:
    """
    Store an order/menu-related question to answer later.
    Use when user asks questions mid-collection (e.g., asking about menu while giving address).
    
    **Use Case:** User mixes address + menu question:
    User: "شارع القلعة مبنى 12. وش أنواع البرجر عندكم؟"
    
    Agent actions:
    1. set_delivery_address(street="القلعة", building="12")
    2. defer_question("وش أنواع البرجر عندكم؟", "menu")
    3. Say: "تمام حفظنا العنوان! بحولك لقسم الطلبات يجاوبك عن أنواع البرجر"
    4. transfer_to_order
    
    Args:
        question: The question text
        category: Type of question ("menu", "order", "price", etc.)
        
    Returns:
        {"success": bool, "question": str, "deferred_questions": list}
    """
    session = SessionStore.get_current()
    
    # Initialize deferred questions if not exists
    if not hasattr(session, 'deferred_questions'):
        session.deferred_questions = []
    
    # Add question with metadata
    session.deferred_questions.append({
        "question": question,
        "category": category,
    })
    
    return {
        "success": True,
        "question": question,
        "category": category,
        "deferred_questions": session.deferred_questions,
        "message": f"تم حفظ السؤال: {question}. سيتم الإجابة عليه عند انتقال للقسم المختص.",
    }

