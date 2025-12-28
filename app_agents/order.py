"""
Order agent: Take order items from menu.
"""

from agents import Agent, handoff
from agents.extensions.handoff_prompt import RECOMMENDED_PROMPT_PREFIX
from config import MODELS
from .prompts import ORDER_PROMPT
from core.filters import filter_order_to_checkout, filter_order_to_location
from tools.menu import search_menu, get_item_details
from tools.order import (
    add_to_order,
    get_current_order,
    remove_from_order,
    modify_order_item,
    store_offered_items,
    select_from_offered,
)
from tools.session_tools import (
    set_customer_name,
    set_phone_number,
    set_order_mode,
    get_pending_items,    
    clear_pending_orders, 
)


def create_order_agent(checkout_agent, location_agent=None):
    """
    Create order agent that handles menu selection and order building.
    
    Args:
        checkout_agent: Checkout agent to hand off to when order is complete
        location_agent: Location agent for switching to delivery mode (optional, set later)
    """
    handoffs = [
        handoff(agent=checkout_agent, input_filter=filter_order_to_checkout),
    ]
    if location_agent is not None:
        handoffs.append(
            handoff(agent=location_agent, input_filter=filter_order_to_location)
        )

    return Agent(
        name="order_agent",
        model=MODELS["order"], 
        instructions=f"{RECOMMENDED_PROMPT_PREFIX}\n{ORDER_PROMPT}",
        tools=[
            search_menu, 
            get_item_details, 
            add_to_order, 
            get_current_order,
            remove_from_order,
            modify_order_item,
            store_offered_items,    
            select_from_offered,    
            set_customer_name,      
            set_phone_number,       
            set_order_mode,         
            get_pending_items,      
            clear_pending_orders,   
        ],
        handoffs=handoffs,
    )
