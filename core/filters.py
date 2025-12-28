"""
Handoff input filters for minimal context transfer between agents.

The filters ensure that:
1. All collected info (name, order mode, district, order items) is preserved
2. Agents don't re-ask for info that's already in the session
3. User's original requests (pending order text) are forwarded
"""
import re
from agents import HandoffInputData
from core.session import SessionStore


def _extract_pending_order_from_message(message: str) -> str | None:
    """
    Extract order-related content from user message.
    
    Examples:
    - "أبي اطلب اثنين كبسه لحم توصيل" → "اثنين كبسه لحم"
    - "حاب اطلب برجر مع بيبسي" → "برجر مع بيبسي"
    
    Returns None if no order items detected.
    """
    # Patterns that indicate order intent, followed by item description
    order_patterns = [
        r"(?:أبي|أبغى|حاب|عايز|بدي)\s*(?:اطلب|أطلب)\s+(.+?)(?:\s+توصيل|\s+استلام|\s+pickup|\s+delivery|$)",
        r"(?:أبي|أبغى|حاب|عايز|بدي)\s+(.+?)(?:\s+توصيل|\s+استلام|$)",
    ]
    
    for pattern in order_patterns:
        match = re.search(pattern, message, re.IGNORECASE)
        if match:
            order_text = match.group(1).strip()
            # Remove delivery/pickup keywords if they leaked in
            order_text = re.sub(r'\b(توصيل|استلام|delivery|pickup)\b', '', order_text).strip()
            if order_text and len(order_text) > 2:  # At least 2 chars
                return order_text
    
    return None


def _build_session_context() -> str:
    """
    Build a comprehensive session context string for handoff.
    
    This ensures receiving agents know what's already been collected.
    """
    try:
        session = SessionStore.get_current()
    except RuntimeError:
        return ""
    
    lines = ["<SESSION_STATE>"]
    
    # Customer info
    if session.customer_name:
        lines.append(f"اسم العميل: {session.customer_name} ✓")
    else:
        lines.append("اسم العميل: غير محدد")
    
    # Phone number - CRITICAL: Include this in ALL handoffs!
    if session.phone_number:
        lines.append(f"رقم الجوال: {session.phone_number} ✓")
    else:
        lines.append("رقم الجوال: غير محدد")
    
    # Order mode
    if session.order_mode:
        mode_ar = "توصيل" if session.order_mode == "delivery" else "استلام"
        lines.append(f"نوع الطلب: {mode_ar}")
    
    # Location (if delivery and confirmed)
    if session.order_mode == "delivery" and session.location_confirmed:
        lines.append(f"الحي: {session.district} ✓")
        lines.append(f"رسوم التوصيل: {session.delivery_fee} ريال")
        lines.append(f"الوقت المتوقع: {session.estimated_time}")
    elif session.order_mode == "delivery" and not session.location_confirmed:
        lines.append("الموقع: غير محدد بعد ⚠️")
    
    # Order items
    if session.order_items:
        lines.append("الطلب الحالي:")
        for item in session.order_items:
            size_text = f" {item.size}" if item.size else ""
            lines.append(f"  • {item.quantity} {item.name_ar}{size_text} - {item.total_price} ريال")
        lines.append(f"المجموع الفرعي: {session.subtotal} ريال")
    else:
        lines.append("الطلب الحالي: فارغ")
    
    # Pending order request
    if session.pending_order_items:
        pending_items = ", ".join(item.get("text", "") for item in session.pending_order_items)
        lines.append(f"⚠️ طلب معلق من العميل: \"{pending_items}\"")
        lines.append("→ يجب معالجة هذا الطلب أولاً!")
    
    # Constraints
    if session.constraints:
        lines.append("قيود مهمة:")
        for c in session.constraints:
            lines.append(f"  ⚠️ {c}")
    
    lines.append("</SESSION_STATE>")
    
    return "\n".join(lines)


def _extract_content_from_message(msg) -> tuple[str | None, str]:
    """
    Extract role and content from a message, handling different SDK types.
    
    The OpenAI Agents SDK may pass:
    - str: Raw string content (treat as user message)
    - dict: {"role": ..., "content": ...}
    - SDK objects with .role and .content attributes
    
    Returns: (role, content) tuple
    """
    if isinstance(msg, str):
        return ("user", msg)
    elif isinstance(msg, dict):
        return (msg.get("role"), msg.get("content", ""))
    elif hasattr(msg, "role") and hasattr(msg, "content"):
        # SDK message object
        role = getattr(msg, "role", None)
        content = getattr(msg, "content", "") or ""
        # Handle content that might be a list (e.g., multimodal)
        if isinstance(content, list):
            content = " ".join(
                part.get("text", "") if isinstance(part, dict) else str(part)
                for part in content
            )
        return (role, content)
    return (None, "")


def _extract_customer_name_from_history(history) -> str | None:
    """
    Extract customer name from conversation history.
    
    Looks for patterns like:
    - "أنا أحمد" / "اسمي أحمد"
    - Greeting with name: "السلام عليكم، أنا محمد"
    
    Returns None if no name found.
    
    NOTE: The SDK's input_history can be:
    - str: A single string (the input)
    - tuple[TResponseInputItem, ...]: A tuple of message items
    
    This is a simplified implementation. Production version should 
    use regex patterns or LLM extraction.
    """
    name_patterns = ["أنا ", "اسمي ", "معك "]
    
    # Handle case where history is just a string
    if isinstance(history, str):
        for pattern in name_patterns:
            if pattern in history:
                idx = history.find(pattern) + len(pattern)
                remaining = history[idx:]
                if remaining:
                    parts = remaining.split()
                    if parts:
                        return parts[0]
        return None
    
    # Handle case where history is a sequence of messages
    if not history:
        return None
    
    for msg in history:
        role, content = _extract_content_from_message(msg)
        if role == "user" and content:
            for pattern in name_patterns:
                if pattern in content:
                    # Extract word after pattern (simplified)
                    idx = content.find(pattern) + len(pattern)
                    remaining = content[idx:]
                    if remaining:
                        parts = remaining.split()
                        if parts:
                            return parts[0]
    return None


def _format_order_for_handoff(order_items) -> str:
    """
    Format order items as compact Arabic text for handoff.
    
    Example output:
    • ٢ برجر كلاسيكي كبير - ٩٠ ريال
    • ١ بيبسي - ٨ ريال
    """
    lines = []
    for item in order_items:
        size_text = f" {item.size}" if item.size else ""
        lines.append(f"• {item.quantity} {item.name_ar}{size_text} - {item.total_price} ريال")
    return "\n".join(lines) if lines else "لا يوجد أصناف"


def filter_greeting_to_location(data: HandoffInputData) -> HandoffInputData:
    """
    Greeting → Location: Transfer context including any pending order.
    
    TRANSFERS:
    - customer_name (extracted from conversation)
    - intent ("delivery")
    - pending_order_text (if user mentioned items like "اثنين كبسه لحم")
    - Last user message for continuity
    
    DROPS:
    - Full greeting conversation
    - Tool call history
    """
    # Extract last user message
    last_user_message = ""
    if isinstance(data.input_history, str):
        last_user_message = data.input_history
    elif data.input_history:
        for msg in reversed(list(data.input_history)):
            role, content = _extract_content_from_message(msg)
            if role == "user" and content:
                last_user_message = content
                break
    
    # Extract customer name
    customer_name = _extract_customer_name_from_history(data.input_history)
    
    # Update session
    try:
        session = SessionStore.get_current()
        if customer_name and not session.customer_name:
            session.customer_name = customer_name
        session.order_mode = "delivery"
        session.intent = "delivery"
        
        # IMPORTANT: Extract and store pending order from user's message
        pending = _extract_pending_order_from_message(last_user_message)
        if pending:
            session.pending_order_items.append({"text": pending, "quantity": 1, "processed": False})
    except RuntimeError:
        pass
    
    # Build context with full session state
    session_context = _build_session_context()
    
    summary = f"""{session_context}

رسالة العميل: {last_user_message}

مهمتك: تحقق من موقع التوصيل. العميل يريد توصيل."""
    
    return HandoffInputData(
        input_history=summary,
        pre_handoff_items=(),
        new_items=(),
    )


def filter_greeting_to_order(data: HandoffInputData) -> HandoffInputData:
    """
    Greeting → Order (pickup): Transfer customer info and pickup intent
    """
    # Extract last user message
    last_user_message = ""
    if isinstance(data.input_history, str):
        last_user_message = data.input_history
    elif data.input_history:
        for msg in reversed(list(data.input_history)):
            role, content = _extract_content_from_message(msg)
            if role == "user" and content:
                last_user_message = content
                break
    
    customer_name = _extract_customer_name_from_history(data.input_history)
    
    # Update session
    try:
        session = SessionStore.get_current()
        if customer_name and not session.customer_name:
            session.customer_name = customer_name
        session.order_mode = "pickup"
        session.intent = "pickup"
        
        # IMPORTANT: Extract and store pending order from user's message
        pending = _extract_pending_order_from_message(last_user_message)
        if pending:
            session.pending_order_items.append({"text": pending, "quantity": 1, "processed": False})
    except RuntimeError:
        pass
    
    # Build context with full session state
    session_context = _build_session_context()
    
    summary = f"""{session_context}

رسالة العميل: {last_user_message}

مهمتك: ساعد العميل في طلبه (استلام من المطعم)."""
    
    return HandoffInputData(
        input_history=summary,
        pre_handoff_items=(),
        new_items=(),
    )


def filter_location_to_order(data: HandoffInputData) -> HandoffInputData:
    """
    Location → Order: Transfer location context + any pending order.
    
    CRITICAL: This is where pending_order_text gets passed to Order agent.
    The Order agent must process this first!
    """
    context = SessionStore.get_current()
    
    # Build context with full session state (includes pending order)
    session_context = _build_session_context()
    
    # Build task description
    task = "مهمتك: ساعد العميل في طلبه."
    pending_items_text = ""
    try:
        session = SessionStore.get_current()
        if session.pending_order_items:
            pending_items_text = ", ".join(item.get("text", "") for item in session.pending_order_items)
    except RuntimeError:
        pass
    
    if pending_items_text:
        task = f"""مهمتك: العميل طلب سابقاً \"{pending_items_text}\".
→ ابحث عن هذه الأصناف وأضفها للطلب أولاً!
→ لا تسأل العميل "شو تبي تطلب" - هو قالك قبل!"""
    
    summary = f"""{session_context}

{task}"""
    
    return HandoffInputData(
        input_history=summary,
        pre_handoff_items=(),
        new_items=(),
    )


def filter_order_to_checkout(data: HandoffInputData) -> HandoffInputData:
    """
    Order → Checkout: Transfer full order details for confirmation.
    """
    # Build context with full session state
    session_context = _build_session_context()
    
    summary = f"""{session_context}

مهمتك: اعرض ملخص الطلب وأكده مع العميل."""
    
    return HandoffInputData(
        input_history=summary,
        pre_handoff_items=(),
        new_items=(),
    )


def filter_order_to_location(data: HandoffInputData) -> HandoffInputData:
    """
    Order → Location: User wants to switch from pickup to delivery.
    
    Preserves order items but switches to delivery mode.
    """
    context = SessionStore.get_current()
    context.order_mode = "delivery"
    context.location_confirmed = False  # Need to reconfirm location
    
    # Get the last user message
    last_user_message = ""
    if isinstance(data.input_history, str):
        last_user_message = data.input_history
    elif data.input_history:
        for msg in reversed(list(data.input_history)):
            role, content = _extract_content_from_message(msg)
            if role == "user" and content:
                last_user_message = content
                break
    
    # Build context with full session state
    session_context = _build_session_context()
    
    summary = f"""{session_context}

رسالة العميل: {last_user_message}

مهمتك: العميل يريد تغيير من استلام إلى توصيل. اسأله عن موقعه."""
    
    return HandoffInputData(
        input_history=summary,
        pre_handoff_items=(),
        new_items=(),
    )


def filter_checkout_to_order(data: HandoffInputData) -> HandoffInputData:
    """
    Checkout → Order: Return to order agent for modifications.
    """
    # Get the last user message
    last_user_message = ""
    if isinstance(data.input_history, str):
        last_user_message = data.input_history
    elif data.input_history:
        for msg in reversed(list(data.input_history)):
            role, content = _extract_content_from_message(msg)
            if role == "user" and content:
                last_user_message = content
                break
    
    # Build context with full session state
    session_context = _build_session_context()
    
    summary = f"""{session_context}

رسالة العميل: {last_user_message}

مهمتك: ⚠️ العميل يريد تعديل طلبه. ساعده في التعديل ثم أكمل للتأكيد."""
    
    return HandoffInputData(
        input_history=summary,
        pre_handoff_items=(),
        new_items=(),
    )


def filter_checkout_to_location(data: HandoffInputData) -> HandoffInputData:
    """
    Checkout → Location: User wants delivery and needs to set/change location.
    
    This happens when:
    - User switches from pickup to delivery
    - User's provided district was not covered
    - User wants to change delivery location
    """
    # Get the last user message
    last_user_message = ""
    if isinstance(data.input_history, str):
        last_user_message = data.input_history
    elif data.input_history:
        for msg in reversed(list(data.input_history)):
            role, content = _extract_content_from_message(msg)
            if role == "user" and content:
                last_user_message = content
                break
    
    # Build context with full session state
    session_context = _build_session_context()
    
    summary = f"""{session_context}

رسالة العميل: {last_user_message}

مهمتك: ⚠️ العميل يريد توصيل. تحقق من موقعه باستخدام check_delivery_district().
- إذا مغطى: أخبره بالرسوم والوقت ثم حوّل للتأكيد (transfer_to_checkout)
- إذا غير مغطى: أخبره واقترح استلام أو حي آخر"""
    
    return HandoffInputData(
        input_history=summary,
        pre_handoff_items=(),
        new_items=(),
    )


def filter_location_to_checkout(data: HandoffInputData) -> HandoffInputData:
    """
    Location → Checkout: Location validated, return to checkout for confirmation.
    
    This happens when:
    - District was validated and delivery fee/time set
    - User came from checkout and now location is confirmed
    """
    # Build context with full session state (now includes confirmed location)
    session_context = _build_session_context()
    
    summary = f"""{session_context}

مهمتك: ⚠️ تم تأكيد موقع التوصيل. اعرض ملخص الطلب واطلب التأكيد النهائي."""
    
    return HandoffInputData(
        input_history=summary,
        pre_handoff_items=(),
        new_items=(),
    )

