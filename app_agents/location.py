"""
Location agent: Collect and validate delivery address.

"""

import json
from pathlib import Path
from agents import Agent, handoff
from agents.extensions.handoff_prompt import RECOMMENDED_PROMPT_PREFIX
from config import MODELS
from .prompts import get_location_prompt
from core.filters import filter_location_to_order, filter_location_to_checkout
from tools.location import check_delivery_district
from tools.session_tools import (
    set_order_mode, 
    set_delivery_address, 
    get_order_summary, 
    defer_question,
)


def _load_delivery_zones() -> list[str]:
    """Load delivery zone names from coverage_zones.json."""
    zones_path = Path(__file__).parent.parent / "data" / "coverage_zones.json"
    try:
        with open(zones_path, "r", encoding="utf-8") as f:
            zones_data = json.load(f)
        return list(zones_data.keys())
    except Exception:
        return ["النرجس", "الياسمين", "العليا"]  # Fallback


def create_location_agent(order_agent, checkout_agent=None):
    """
    Create location agent that validates delivery coverage.

    IMPORTANT: This agent only has location-related tools!
    - NO set_customer_name (prevents street names from being saved as names)
    - NO set_phone_number (not its job)
    - NO set_pending_order (not its job)
    """
    zones = _load_delivery_zones()
    location_prompt = get_location_prompt(zones)
    
    handoffs_list = [
        handoff(
            agent=order_agent,
            input_filter=filter_location_to_order,
        ),
    ]
    
    if checkout_agent:
        handoffs_list.append(
            handoff(
                agent=checkout_agent,
                input_filter=filter_location_to_checkout,
            )
        )
    
    return Agent(
        name="location_agent",
        model=MODELS["location"],
        instructions=f"{RECOMMENDED_PROMPT_PREFIX}\n{location_prompt}",
        tools=[
            check_delivery_district, 
            set_delivery_address,  
            set_order_mode, 
            get_order_summary, 
            defer_question, 
        ],
        handoffs=handoffs_list,
    )
