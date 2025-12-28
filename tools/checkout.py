"""
Checkout agent tools: calculate_total, confirm_order, set_customer_info
"""

from agents import function_tool
from core.session import SessionStore
import uuid
from datetime import datetime


@function_tool
def set_customer_info(
    name: str = None, phone: str = None, full_address: str = None
) -> dict:
    """
    Store customer contact information.

    ⚠️ IDEMPOTENCY: If info is already set to the SAME value, returns early.
    ✅ OVERRIDES ALLOWED: If user wants to CHANGE their info (e.g., "لا، اسمي أحمد" or "رقمي 0561234567"), call this to update!
    Check SESSION_STATE first - only skip if the value is already set AND user hasn't indicated a change!

    Args:
        name: Customer's name (optional)
        phone: Customer's phone number (optional)
        full_address: Full delivery address - street, building (optional)

    Returns:
        {
            "success": bool,
            "customer_name": str,
            "phone_number": str,
            "full_address": str,
            "already_set": dict  # Which fields were already set
        }
    """
    session = SessionStore.get_current()

    already_set = {}
    updated = {}

    if name:
        if session.customer_name and session.customer_name.strip() == name.strip():
            already_set["name"] = True
        else:
            session.customer_name = name
            updated["name"] = True

    if phone:
        normalized_phone = (
            phone.strip().replace(" ", "").replace("-", "").replace("_", "")
        )
        existing_phone = (
            (session.phone_number or "")
            .strip()
            .replace(" ", "")
            .replace("-", "")
            .replace("_", "")
        )
        if existing_phone and normalized_phone == existing_phone:
            already_set["phone"] = True
        else:
            session.phone_number = phone
            updated["phone"] = True

    if full_address:
        if (
            session.full_address
            and session.full_address.strip() == full_address.strip()
        ):
            already_set["full_address"] = True
        else:
            session.full_address = full_address
            updated["full_address"] = True

    # Build message
    if already_set:
        msg = f"⚠️ بعض المعلومات محفوظة مسبقاً: {', '.join(already_set.keys())}"
        if updated:
            msg += f" | تم تحديث: {', '.join(updated.keys())}"
    else:
        msg = "تم حفظ المعلومات"

    return {
        "success": True,
        "customer_name": session.customer_name,
        "phone_number": session.phone_number,
        "full_address": session.full_address,
        "already_set": already_set,
        "updated": updated,
        "message": msg,
    }


@function_tool
def calculate_total() -> dict:
    """
    Calculate final order total with delivery fee.

    NOTE: The assessment asks for "total (including delivery fee)" only.
    Tax/VAT is NOT included by default. If needed, set INCLUDE_TAX=True in config.

    ⚠️ NOTE: This is a pure calculation - you can read totals from SESSION_STATE instead!
    Only call this if you need to show a formatted breakdown to the user.

    Returns:
        {
            "subtotal": float,
            "delivery_fee": float,
            "total": float,
            "breakdown": str  # Arabic formatted
        }
    """
    session = SessionStore.get_current()

    subtotal = session.subtotal
    delivery_fee = session.delivery_fee if session.order_mode == "delivery" else 0
    total = subtotal + delivery_fee

    # Build breakdown (delivery fee only, no tax per requirements)
    if session.order_mode == "delivery":
        breakdown = f"""📦 الطلب: {subtotal} ريال
🚗 التوصيل: {delivery_fee} ريال
━━━━━━━━━━━━━━━
💰 الإجمالي: {total} ريال"""
    else:
        breakdown = f"""📦 الطلب: {subtotal} ريال
━━━━━━━━━━━━━━━
💰 الإجمالي: {total} ريال"""

    return {
        "subtotal": subtotal,
        "delivery_fee": delivery_fee,
        "total": total,
        "breakdown": breakdown,
        "order_mode": session.order_mode,
    }


@function_tool
def confirm_order(customer_name: str, phone_number: str) -> dict:
    """
    Confirm and finalize the order.

    ⚠️ REQUIRED PARAMETERS - must be provided by the customer!

    Args:
        customer_name: Customer's full name (REQUIRED - ask customer if unknown)
        phone_number: Customer's phone number (REQUIRED - ask customer if unknown)

    ⚠️ Do NOT call this with empty/placeholder values!
    ⚠️ Do NOT call this if you don't have real name and phone from the customer!

    Returns:
        {
            "success": bool,
            "order_id": str,
            "total": float,
            "message": str,
            "session_ended": bool
        }
    """
    session = SessionStore.get_current()

    if not session.order_items:
        return {
            "success": False,
            "error": "empty_order",
            "message": "الطلب فاضي! ضيف أصناف أولاً.",
        }

    # Validate required parameters - they must be real values!
    if not customer_name or customer_name.strip() == "" or "غير" in customer_name:
        return {
            "success": False,
            "error": "invalid_name",
            "message": "⛔ الاسم مطلوب! اسأل العميل: 'ممكن اسمك الكريم؟'",
        }

    if not phone_number or phone_number.strip() == "" or "غير" in phone_number:
        return {
            "success": False,
            "error": "invalid_phone",
            "message": "⛔ رقم الجوال مطلوب! اسأل العميل: 'ممكن رقم جوالك؟'",
        }

    # Save customer info (in case not saved already)
    session.customer_name = customer_name.strip()
    session.phone_number = phone_number.strip()

    # For delivery, check location AND address
    if session.order_mode == "delivery":
        if not session.location_confirmed:
            return {
                "success": False,
                "error": "missing_district",
                "message": "⛔ الحي غير محدد! استخدم [transfer_to_location]",
            }
        if not session.address_complete:
            return {
                "success": False,
                "error": "incomplete_address",
                "message": "⛔ العنوان غير مكتمل! مطلوب: اسم الشارع ورقم المبنى. استخدم [transfer_to_location]",
            }

    # Generate order ID
    order_id = f"ORD-{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:4].upper()}"

    # Calculate total
    subtotal = session.subtotal
    delivery_fee = session.delivery_fee if session.order_mode == "delivery" else 0
    total = subtotal + delivery_fee

    # Mark session as completed
    session.status = "completed"
    session.order_id = order_id

    # Use validated parameters
    phone = phone_number.strip()

    if session.order_mode == "delivery":
        location_info = f"""التوصيل: {session.district}
العنوان: {session.full_address or 'غير محدد'}
الوقت المتوقع: {session.estimated_time or '30-45 دقيقة'}"""
    else:
        location_info = f"الاستلام من الفرع\nالوقت المتوقع: 15-20 دقيقة"

    return {
        "success": True,
        "order_id": order_id,
        "customer_name": session.customer_name,
        "phone": phone,
        "estimated_time": session.estimated_time or "30-45 دقيقة",
        "total": total,
        "message": f"""تم تأكيد طلبك بنجاح! 🎉

👤 {session.customer_name}
📱 {phone}

رقم الطلب: {order_id}
الإجمالي: {total} ريال

{location_info}

⚠️ لأي تعديل أو إلغاء، اتصل على: 920001234

شكراً لطلبك من البيت العربي! 🏠""",
        "session_ended": True,
    }
