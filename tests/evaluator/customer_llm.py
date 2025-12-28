"""
LLM-powered customer simulator.

Uses an LLM to simulate a human customer interacting with the restaurant agent.
The customer LLM adapts its responses based on the agent's replies, making
tests more realistic and robust.
"""

import json
from dataclasses import dataclass
from openai import AsyncOpenAI

from config import OPENROUTER_API_KEY, OPENROUTER_BASE_URL


# Customer simulation models (fast, cheap models work best)
CUSTOMER_MODELS = {
    "gpt-5.2": "openai/gpt-5.2",
    "gpt-4o": "openai/gpt-4o",  # Fallback
    "claude-4.5-opus": "anthropic/claude-opus-4.5",
    "gemini-3-pro": "google/gemini-3-pro-preview",
    "gemini-3-flash": "google/gemini-3-flash-preview",
    "kimi-k2": "moonshotai/kimi-k2-thinking"
}

DEFAULT_CUSTOMER_MODEL = "gemini-3-flash"


@dataclass
class CustomerPersona:
    """Defines how the simulated customer should behave."""
    scenario_id: str
    goal: str  # What the customer wants to achieve
    personality: str  # How they communicate
    constraints: list[str]  # Things they must do/not do
    success_criteria: dict  # How to know the goal is achieved
    max_turns: int = 15


# Customer personas for each scenario
CUSTOMER_PERSONAS = {
    "simple_pickup": CustomerPersona(
        scenario_id="simple_pickup",
        goal="Order a beef burger for pickup and complete the order",
        personality="Simple, direct Saudi customer. Uses Gulf Arabic dialect. Gives short answers.",
        constraints=[
            "Want pickup (استلام), not delivery",
            "Order one beef burger (برجر لحم)",
            "Give name when asked",
            "Give phone when asked",
            "Confirm the order at the end",
        ],
        success_criteria={
            "order_mode": "pickup",
            "has_items": True,
            "order_confirmed": True,
        },
    ),
    
    "simple_delivery": CustomerPersona(
        scenario_id="simple_delivery",
        goal="Order a burger for delivery to النرجس district",
        personality="Friendly Saudi customer. Uses Gulf dialect. Cooperative.",
        constraints=[
            "Want delivery (توصيل)",
            "Live in النرجس district",
            "Give street and building when asked",
            "Order beef burger",
            "Confirm order",
        ],
        success_criteria={
            "order_mode": "delivery",
            "has_items": True,
            "has_address": True,
        },
    ),
    
    "pickup_to_delivery": CustomerPersona(
        scenario_id="pickup_to_delivery",
        goal="Start with pickup, then change to delivery at the end",
        personality="Indecisive customer. Changes mind. Uses Gulf Arabic.",
        constraints=[
            "Initially say pickup (استلام)",
            "Order burger and shawarma",
            "At checkout, change mind and request delivery (توصيل)",
            "Give address for الياسمين",
            "Complete the order",
        ],
        success_criteria={
            "order_mode": "delivery",
            "mode_switched": True,
        },
    ),
    
    "delivery_to_pickup": CustomerPersona(
        scenario_id="delivery_to_pickup",
        goal="Start with delivery, then switch to pickup to save money",
        personality="Price-conscious customer. Switches to pickup when sees delivery fee.",
        constraints=[
            "Initially say delivery",
            "Give address in العليا",
            "Order shawarma",
            "When you see the total with delivery fee, say you want pickup instead",
            "Complete the order",
        ],
        success_criteria={
            "order_mode": "pickup",
            "mode_switched": True,
        },
    ),
    
    "complex_full_flow": CustomerPersona(
        scenario_id="complex_full_flow",
        goal="Complex order with modifications and mode switches",
        personality="Demanding customer. Changes items, quantities, and mode multiple times.",
        constraints=[
            "Start with pickup",
            "Order multiple items: burger, shawarma, tea",
            "Add pizza",
            "Remove some tea",
            "Switch to delivery",
            "Give address",
            "Then switch back to pickup (cheaper)",
            "Add hummus",
            "Remove shawarma",
            "Complete order",
        ],
        success_criteria={
            "order_mode": "pickup",
            "items_modified": True,
        },
    ),
    
    "arabic_dialect": CustomerPersona(
        scenario_id="arabic_dialect",
        goal="Test dialect understanding with Saudi slang",
        personality="Young Saudi using heavy dialect and slang. Says things like 'وش عندكم', 'عطني', 'خلاص بس'.",
        constraints=[
            "Use heavy Gulf/Saudi dialect",
            "Ask 'وش عندكم؟' to see menu",
            "Use 'عطني' instead of 'أريد'",
            "Say phone number as words: 'خمسه خمسه واحد...'",
            "Complete a pickup order",
        ],
        success_criteria={
            "order_confirmed": True,
        },
    ),
    
    "code_switching": CustomerPersona(
        scenario_id="code_switching",
        goal="Mix Arabic and English freely",
        personality="Bilingual Saudi. Mixes English and Arabic naturally.",
        constraints=[
            "Mix English and Arabic: 'hi ابي order'",
            "Use English item names: 'chicken burger', 'hummus'",
            "Use 'please', 'thanks' in English",
            "Complete a pickup order",
        ],
        success_criteria={
            "order_confirmed": True,
        },
    ),
    
    "error_recovery": CustomerPersona(
        scenario_id="error_recovery",
        goal="Request unavailable items, make typos, then recover",
        personality="Customer who makes mistakes. Asks for items not on menu.",
        constraints=[
            "First ask for 'سوشي' (not on menu)",
            "Then ask for 'ربيان' (not on menu)",
            "Accept agent's suggestions",
            "Make a typo: 'برقر' instead of 'برجر'",
            "Complete order",
        ],
        success_criteria={
            "handled_unavailable": True,
            "order_confirmed": True,
        },
    ),
    
    "ambiguous_items": CustomerPersona(
        scenario_id="ambiguous_items",
        goal="Order ambiguous items that need clarification",
        personality="Vague customer. Says just 'burger' without specifying type.",
        constraints=[
            "Say just 'برجر' - don't specify type",
            "When shown options, pick one",
            "Say just 'بيتزا' - don't specify type", 
            "When shown options, pick one",
            "Complete order",
        ],
        success_criteria={
            "showed_options": True,
            "order_confirmed": True,
        },
    ),
    
    "edge_cases": CustomerPersona(
        scenario_id="edge_cases",
        goal="Test cancellation, restart, and asking for complaint number",
        personality="Difficult customer. Cancels order, restarts, asks about complaints.",
        constraints=[
            "Start ordering (delivery, burger, shawarma)",
            "Cancel the entire order ('الغي الطلب كله')",
            "Start fresh ('ابي اطلب من جديد')",
            "This time do pickup",
            "Ask for complaint number ('وش رقم الشكاوي؟')",
            "Complete the order",
        ],
        success_criteria={
            "order_cancelled_and_restarted": True,
            "order_confirmed": True,
        },
    ),
    
    # NEW PERSONAS - Testing recent improvements
    "empty_order_prevention": CustomerPersona(
        scenario_id="empty_order_prevention",
        goal="Try to confirm order before adding items, then add items and complete",
        personality="Impatient customer. Tries to rush through without adding items.",
        constraints=[
            "Say you want pickup",
            "Try to confirm/complete order WITHOUT ordering anything ('تمام اعتمد الطلب')",
            "When agent rejects, add a beef burger",
            "Then actually complete the order properly",
        ],
        success_criteria={
            "order_mode": "pickup",
            "has_items": True,
            "order_confirmed": True,
            "rejected_empty_confirmation": True,
        },
    ),
    
    "multiple_pending_items": CustomerPersona(
        scenario_id="multiple_pending_items",
        goal="Order multiple items at once in greeting, then clarify each during order phase",
        personality="Hungry customer. Lists many items upfront.",
        constraints=[
            "At the very start, say you want delivery AND list multiple items: '2 burgers, 3 pizzas, shawarma'",
            "Give النرجس as district and full address",
            "When order agent asks, clarify burger type, pizza type, shawarma type",
            "Complete the order",
        ],
        success_criteria={
            "order_mode": "delivery",
            "has_items": True,
            "item_count_min": 3,
            "processed_all_pending": True,
        },
    ),
    
    "smart_location_routing": CustomerPersona(
        scenario_id="smart_location_routing",
        goal="Request delivery without mentioning items, then add items after giving address",
        personality="Customer who forgets to mention food. Focuses on delivery first.",
        constraints=[
            "Say you want delivery but DON'T mention any food",
            "Give النرجس district and full address",
            "After address is collected, agent should route you to order agent",
            "THEN order a chicken burger",
            "Complete the order",
        ],
        success_criteria={
            "order_mode": "delivery",
            "has_items": True,
            "has_address": True,
            "location_routed_correctly": True,
        },
    ),
}


CUSTOMER_SYSTEM_PROMPT = '''You are simulating a Saudi Arabian customer ordering from a restaurant.

## Your Goal
{goal}

## Your Personality
{personality}

## What You Must Do
{constraints}

## Rules
1. ONLY respond as the customer - never break character
2. Use Gulf/Saudi Arabic dialect
3. Give SHORT responses like a real customer (1-2 sentences max)
4. React naturally to what the agent says
5. If the agent asks you a question, answer it
6. If you've achieved your goal, say something to end the conversation (like "تمام شكرا" or confirm the order)
7. Do NOT explain what you're doing - just be the customer

## Current Conversation
The agent's last message is provided. Respond as the customer would.

## Success Criteria
You've succeeded when: {success_criteria}

Respond with ONLY what the customer would say. No explanations, no quotes, just the message.
'''


class CustomerLLM:
    """Simulates a human customer using an LLM."""
    
    def __init__(self, model: str = DEFAULT_CUSTOMER_MODEL):
        self.model = CUSTOMER_MODELS.get(model, model)
        self.client = AsyncOpenAI(
            base_url=OPENROUTER_BASE_URL,
            api_key=OPENROUTER_API_KEY,
            default_headers={
                "HTTP-Referer": "https://arabic-restaurant-agent.com",
                "X-Title": "Customer Simulator",
            },
        )
        self.conversation_history: list[dict] = []
    
    def reset(self):
        """Clear conversation history for new scenario."""
        self.conversation_history = []
    
    async def get_response(
        self,
        persona: CustomerPersona,
        agent_message: str,
        turn_number: int,
    ) -> str:
        """
        Generate customer response based on agent's message.
        
        Args:
            persona: Customer behavior definition
            agent_message: What the restaurant agent just said
            turn_number: Current turn in conversation
            
        Returns:
            Customer's response message
        """
        # Build system prompt with persona
        constraints_text = "\n".join(f"- {c}" for c in persona.constraints)
        system_prompt = CUSTOMER_SYSTEM_PROMPT.format(
            goal=persona.goal,
            personality=persona.personality,
            constraints=constraints_text,
            success_criteria=json.dumps(persona.success_criteria, ensure_ascii=False),
        )
        
        # Add agent message to history
        self.conversation_history.append({
            "role": "assistant",  # Agent's message
            "content": f"[المطعم]: {agent_message}",
        })
        
        # Build messages for LLM
        messages = [
            {"role": "system", "content": system_prompt},
        ]
        
        # Add conversation history
        for msg in self.conversation_history[-10:]:  # Last 10 messages
            messages.append(msg)
        
        # Add instruction for this turn
        if turn_number == 1:
            messages.append({
                "role": "user",
                "content": "أنت الآن تبدأ المحادثة. قل شيء لبدء طلبك.",
            })
        else:
            messages.append({
                "role": "user",
                "content": "الآن رد على رسالة المطعم كعميل.",
            })
        
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=150,
                temperature=0.7,
            )
            
            customer_message = response.choices[0].message.content.strip()
            
            # Clean up response (remove quotes, prefixes)
            customer_message = customer_message.strip('"\'')
            if customer_message.startswith("[العميل]:"):
                customer_message = customer_message[9:].strip()
            
            # Add to history
            self.conversation_history.append({
                "role": "user",
                "content": f"[العميل]: {customer_message}",
            })
            
            return customer_message
            
        except Exception as e:
            return f"عذرا، فيه مشكلة ({e})"
    
    async def get_initial_message(self, persona: CustomerPersona) -> str:
        """Generate the customer's opening message to start the conversation."""
        constraints_text = "\n".join(f"- {c}" for c in persona.constraints)
        system_prompt = CUSTOMER_SYSTEM_PROMPT.format(
            goal=persona.goal,
            personality=persona.personality,
            constraints=constraints_text,
            success_criteria=json.dumps(persona.success_criteria, ensure_ascii=False),
        )
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": "أنت الآن تبدأ المحادثة مع المطعم. قل شيء لبدء طلبك."},
        ]
        
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=100,
                temperature=0.7,
            )
            
            customer_message = response.choices[0].message.content.strip()
            customer_message = customer_message.strip('"\'')
            
            # Add to history
            self.conversation_history.append({
                "role": "user",
                "content": f"[العميل]: {customer_message}",
            })
            
            return customer_message
            
        except Exception as e:
            return "السلام عليكم، ابي اطلب"


def get_persona(scenario_id: str) -> CustomerPersona | None:
    """Get customer persona for a scenario."""
    return CUSTOMER_PERSONAS.get(scenario_id)


def get_all_personas() -> list[CustomerPersona]:
    """Get all customer personas."""
    return list(CUSTOMER_PERSONAS.values())
