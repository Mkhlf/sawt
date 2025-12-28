"""
Agents module: Export all agent creation functions.
"""

from agents import handoff
from core.filters import (
    filter_checkout_to_order,
    filter_order_to_location,
    filter_checkout_to_location,
    filter_location_to_checkout,
)

from .greeting import create_greeting_agent
from .location import create_location_agent
from .order import create_order_agent
from .checkout import create_checkout_agent


def create_agents():
    """
    Create all agents with proper dependencies.

    Handles circular dependencies by creating agents first, then fixing references.

    Returns:
        tuple: (greeting_agent, location_agent, order_agent, checkout_agent)
    """
    # Create in reverse dependency order to handle circular refs
    checkout_agent = create_checkout_agent(order_agent=None, location_agent=None)
    order_agent = create_order_agent(checkout_agent, location_agent=None)
    location_agent = create_location_agent(order_agent)
    greeting_agent = create_greeting_agent(location_agent, order_agent)

    # Add checkout -> order handoff
    checkout_agent.handoffs.append(
        handoff(
            agent=order_agent,
            input_filter=filter_checkout_to_order,
            tool_name_override="transfer_to_order",
            tool_description_override="حول للطلبات عندما يريد العميل تعديل أصناف طلبه",
        )
    )
    # Add checkout -> location handoff
    checkout_agent.handoffs.append(
        handoff(
            agent=location_agent,
            input_filter=filter_checkout_to_location,
            tool_name_override="transfer_to_location",
            tool_description_override="حول للموقع عندما يريد العميل توصيل ويحتاج تحديد الحي",
        )
    )
    # Add order -> location handoff
    order_agent.handoffs.append(
        handoff(agent=location_agent, input_filter=filter_order_to_location)
    )
    # Add location -> checkout handoff (for when coming from checkout)
    location_agent.handoffs.append(
        handoff(
            agent=checkout_agent,
            input_filter=filter_location_to_checkout,
            tool_name_override="transfer_to_checkout",
            tool_description_override="حول للتأكيد بعد تحديد موقع التوصيل",
        )
    )

    return greeting_agent, location_agent, order_agent, checkout_agent
