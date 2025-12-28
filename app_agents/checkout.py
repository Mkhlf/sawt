"""
Checkout agent: Summarize order and confirm.
"""

from agents import Agent, handoff
from agents.extensions.handoff_prompt import RECOMMENDED_PROMPT_PREFIX
from config import MODELS
from .prompts import CHECKOUT_PROMPT
from core.filters import filter_checkout_to_order
from tools.checkout import calculate_total, confirm_order, set_customer_info
from tools.session_tools import get_session_state, set_order_mode


def create_checkout_agent(order_agent=None, location_agent=None):
    """
    Create checkout agent that finalizes orders.

    Args:
        order_agent: Order agent to return to for modifications (optional, set later)
    """
    handoffs = []
    if order_agent is not None:
        handoffs.append(
            handoff(
                agent=order_agent,
                input_filter=filter_checkout_to_order,
                tool_name_override="transfer_to_order",
                tool_description_override="حول للطلبات عندما يريد العميل تعديل أصناف طلبه (إضافة/حذف/تعديل)",
            )
        )
    if location_agent is not None:
        from core.filters import filter_checkout_to_location

        handoffs.append(
            handoff(
                agent=location_agent,
                input_filter=filter_checkout_to_location,
                tool_name_override="transfer_to_location",
                tool_description_override="حول للموقع عندما يريد العميل توصيل ويحتاج تحديد/تغيير الحي",
            )
        )

    return Agent(
        name="checkout_agent",
        model=MODELS["checkout"],
        instructions=f"{RECOMMENDED_PROMPT_PREFIX}\n{CHECKOUT_PROMPT}",
        tools=[
            calculate_total,
            confirm_order,
            set_customer_info,
            get_session_state,
            set_order_mode,  # Allow changing delivery ↔ pickup
        ],
        handoffs=handoffs,
    )
