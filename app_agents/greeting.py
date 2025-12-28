"""
Greeting agent: Welcome user and determine intent.
"""
from agents import Agent, handoff
from agents.extensions.handoff_prompt import RECOMMENDED_PROMPT_PREFIX
from config import MODELS
from .prompts import GREETING_PROMPT
from core.filters import filter_greeting_to_location, filter_greeting_to_order
from tools.session_tools import (
    set_order_mode,
    set_customer_name,
    set_phone_number,
    add_pending_item, 
)


def create_greeting_agent(location_agent, order_agent):
    """
    Create greeting agent that welcomes users and routes them.
    
    Args:
        location_agent: Location agent for delivery orders
        order_agent: Order agent for pickup orders
    """
    return Agent(
        name="greeting_agent",
        model=MODELS["greeting"],
        instructions=f"{RECOMMENDED_PROMPT_PREFIX}\n{GREETING_PROMPT}",
        tools=[
            set_order_mode,      # Capture delivery/pickup intent
            set_customer_name,   # Capture name if provided
            set_phone_number,    # Capture phone if provided
            add_pending_item,    # Store order items for later (structured)
        ],
        handoffs=[
            handoff(
                agent=location_agent,
                tool_name_override="transfer_to_location",
                tool_description_override="حول للموقع عندما يريد العميل توصيل",
                input_filter=filter_greeting_to_location,
            ),
            handoff(
                agent=order_agent,
                tool_name_override="transfer_to_order", 
                tool_description_override="حول للطلب عندما يريد العميل استلام",
                input_filter=filter_greeting_to_order,
            ),
        ]
    )

