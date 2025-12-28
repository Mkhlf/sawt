"""
Main entry point for Arabic Restaurant Ordering Agent.
"""

import argparse
import asyncio
import re
import time
from agents import (
    Runner,
    RunConfig,
    RunHooks,
    set_default_openai_api,
    set_tracing_disabled,
)

from config import OPENROUTER_API_KEY, LOG_LEVEL
from core.provider import OpenRouterModelProvider
from core.session import SessionStore, Session
from core.logging import StructuredLogger
from core.menu_search import MenuSearchEngine
from app_agents import create_agents

import logging
import sys

# Logging will be configured later based on CLI args
logger = logging.getLogger(__name__)

# RTL print function - will be set based on command-line argument
print_rtl = None

# Initialize once at startup
set_default_openai_api("chat_completions")
set_tracing_disabled(True)

provider = OpenRouterModelProvider(OPENROUTER_API_KEY)
structured_logger = StructuredLogger()
menu_engine = MenuSearchEngine("data/menu.json", OPENROUTER_API_KEY)

# Flag to control structured logging output
ENABLE_STRUCTURED_LOGS = True


class LoggingHooks(RunHooks):
    """
    Custom hooks for logging agent operations.
    Captures tool calls, handoffs, and agent transitions.
    """

    def __init__(self, structured_logger: StructuredLogger):
        self.structured_logger = structured_logger
        self._tool_start_times = {}  # Track tool call durations

    async def on_agent_start(self, context, agent):
        logging.debug(f"[AGENT START] {agent.name}")
        
        # NOTE: Actual truncation is handled by RunConfig.call_model_input_filter
        # using core.truncation_filter.truncation_filter
        pass


    async def on_agent_end(self, context, agent, output):
        logging.debug(f"[AGENT END] {agent.name}")


    async def on_tool_start(self, context, agent, tool):
        tool_name = getattr(tool, "name", str(tool))
        self._tool_start_times[tool_name] = time.time()
        # Note: Parameters logged in on_tool_end when we have the full result

    async def on_tool_end(self, context, agent, tool, result):
        tool_name = getattr(tool, "name", str(tool))
        start_time = self._tool_start_times.pop(tool_name, time.time())
        duration_ms = int((time.time() - start_time) * 1000)

        # Get session for logging
        try:
            session = SessionStore.get_current()
            session_id = session.session_id
        except RuntimeError:
            session_id = "unknown"

        # Parse result for logging
        try:
            import json
            result_dict = (
                json.loads(result)
                if isinstance(result, str)
                else result if isinstance(result, dict) else {"raw": str(result)[:200]}
            )
        except:
            result_dict = {"raw": str(result)[:200]}

        # Assessment-compliant format: TOOL: name({params}) and TOOL_RESULT: {result}
        # Note: Full params not available in hook, showing result summary
        logging.info(f"TOOL: {tool_name}")
        
        # Compact result logging (assessment format)
        result_summary = str(result_dict)[:150] if result_dict else "{}"
        logging.info(f"TOOL_RESULT: {result_summary}")

        if ENABLE_STRUCTURED_LOGS:
            self.structured_logger.log_tool_call(
                session_id=session_id,
                agent=agent.name,
                tool=tool_name,
                params={},  # Tool params not easily accessible from hook
                result=result_dict,
                duration_ms=duration_ms,
            )
            
        # Explicit signal for session end
        if tool_name == "confirm_order":
            logging.info("[SESSION_END]")


    async def on_handoff(self, context, from_agent, to_agent):
        # Assessment-compliant handoff logging
        from_name = from_agent.name.replace("_agent", "")
        to_name = to_agent.name.replace("_agent", "")
        
        # Calculate context size from usage stats (most accurate source)
        total_tokens = 0
        message_count = 0
        
        if hasattr(context, 'usage'):
            # usage.input_tokens represents the context size of the last request
            if hasattr(context.usage, 'total_tokens'):
                total_tokens = context.usage.total_tokens
            # Or try valid request entries
            elif hasattr(context.usage, 'request_usage_entries') and context.usage.request_usage_entries:
                total_tokens = context.usage.request_usage_entries[-1].input_tokens

        try:
            session = SessionStore.get_current()

            if hasattr(session, 'conversation_history') and isinstance(session.conversation_history, list):
                message_count = len(session.conversation_history)
                logging.info(f"CONTEXT: Transferred {message_count} messages (est. {total_tokens} tokens)")
            else:
                logging.info(f"CONTEXT: (est. {total_tokens} tokens)")
            
            # Log memory/session state
            memory = {
                "customer_name": session.customer_name or "not_set",
                "phone": session.phone_number or "not_set",
                "order_mode": session.order_mode or "not_set",
                "district": session.district or "not_set",
                "items_count": len(session.order_items)
            }
            logging.info(f"MEMORY: {memory}")
            
            # Structured logs for testing
            if ENABLE_STRUCTURED_LOGS:
                self.structured_logger.log_handoff(
                    session_id=session.session_id,
                    from_agent=from_agent.name,
                    to_agent=to_agent.name,
                    handoff_messages=[],
                    session_context={
                        "customer_name": session.customer_name,
                        "intent": session.intent,
                        "order_mode": session.order_mode,
                        "district": session.district,
                        "location_confirmed": session.location_confirmed,
                        "order_items_count": len(session.order_items),
                    },
                )
        except RuntimeError:
            pass


# Create logging hooks instance
logging_hooks = LoggingHooks(structured_logger)

# Make menu_engine available to tools
import tools.menu
import tools.order

tools.menu.menu_engine = menu_engine
tools.order.menu_engine = menu_engine

# Create agents - keep references to all of them for routing
greeting_agent, location_agent, order_agent, checkout_agent = create_agents()

# Agent mapping for routing
AGENTS = {
    "greeting": greeting_agent,
    "location": location_agent,
    "order": order_agent,
    "checkout": checkout_agent,
}


def _build_session_context_for_input(session: Session) -> str:
    """
    Build session context to inject into user message.
    This ensures the agent knows what's already been collected.
    """
    lines = ["<SESSION_STATE>"]

    # Customer info
    lines.append(f"اسم العميل: {session.customer_name or 'غير محدد'}")
    lines.append(f"رقم الجوال: {session.phone_number or 'غير محدد'}")

    # Order mode
    if session.intent:
        mode_ar = "توصيل" if session.order_mode == "delivery" else "استلام"
        lines.append(f"نوع الطلب: {mode_ar} ✓")
    else:
        lines.append("نوع الطلب: غير محدد")

    # Location
    if session.order_mode == "delivery":
        if session.location_confirmed:
            lines.append(f"الحي: {session.district} ✓")
            # Show address details
            if session.street_name:
                lines.append(f"الشارع: {session.street_name}")
            else:
                lines.append("الشارع: غير محدد ⚠️")
            if session.building_number:
                lines.append(f"رقم المبنى: {session.building_number}")
            else:
                lines.append("رقم المبنى: غير محدد ⚠️")
            if session.additional_info:
                lines.append(f"معلومات إضافية: {session.additional_info}")
            if session.address_complete:
                lines.append(f"العنوان مكتمل: نعم ✓")
            else:
                lines.append(f"العنوان مكتمل: لا ⚠️ (مطلوب الشارع ورقم المبنى)")
            lines.append(f"رسوم التوصيل: {session.delivery_fee} ريال")
            lines.append(f"الوقت المتوقع: {session.estimated_time}")
        else:
            lines.append("الموقع: غير محدد بعد ⚠️")

    # Order items
    if session.order_items:
        lines.append("الطلب الحالي:")
        for item in session.order_items:
            size_text = f" {item.size}" if item.size else ""
            lines.append(
                f"  • {item.quantity} {item.name_ar}{size_text} - {item.total_price} ريال"
            )
        lines.append(f"المجموع الفرعي: {session.subtotal} ريال")
    else:
        lines.append("الطلب الحالي: فارغ")

    # Pending order
    if session.pending_order_items:
        pending_items = ", ".join(item.get("text", "") for item in session.pending_order_items)
        lines.append(f'⚠️ طلب معلق: \"{pending_items}\"')

    # Constraints
    if session.constraints:
        lines.append("قيود مهمة:")
        for c in session.constraints:
            lines.append(f"  ⚠️ {c}")

    lines.append("</SESSION_STATE>")
    return "\n".join(lines)


def _determine_current_agent(session: Session) -> str:
    """
    Determine which agent should handle the next message based on session state.

    Flow logic:
    - No intent yet → greeting
    - Intent=delivery, location not confirmed → location
    - Has order items + location ready → checkout
    - Intent set, ready to order → order

    Special cases:
    - If at location agent but user switched to pickup → respect that
    - Conversation continuity: stay with current agent when appropriate
    """
    # Stay with the current agent if set (respects conversation continuity)
    if session.current_agent:
        # Special handling for location agent
        if session.current_agent == "location":
            # If user switched to pickup, leave location agent!
            if session.order_mode == "pickup":
                if session.order_items:
                    return "checkout"
                return "order"

            # Stay with location agent until BOTH district AND address are complete
            # This ensures we collect the full address (street + building) before moving on
            if not session.location_confirmed:
                return "location"  # District not confirmed yet

            if not session.address_complete:
                return (
                    "location"  # District confirmed but street/building not collected
                )

            # Both confirmed, go to checkout if has items, else order
            if session.order_items:
                return "checkout"
            return "order"

        # For other agents, stay with them unless state requires change
        # Checkout: stay if has items
        if session.current_agent == "checkout" and session.order_items:
            return "checkout"

        # Order: stay if ordering in progress
        if session.current_agent == "order":
            # But if needs location for delivery, go there
            if session.order_mode == "delivery" and not session.location_confirmed:
                return "location"
            return "order"

        # Default: stay with current agent
        return session.current_agent

    # If no intent established yet
    if not session.intent:
        return "greeting"

    # If delivery but location/address not complete
    if session.order_mode == "delivery":
        if not session.location_confirmed or not session.address_complete:
            return "location"

    # If has order items and location ready (or pickup) → checkout
    location_ready = (
        session.location_confirmed and session.address_complete
    ) or session.order_mode == "pickup"
    if session.order_items and location_ready:
        return "checkout"

    # If location complete or pickup mode → order
    if location_ready:
        return "order"

    return "greeting"


# Constraint detection patterns
CONSTRAINT_PATTERNS = [
    (r"حساسية.*من (.+)", "حساسية من {match}"),
    (r"(نباتي|vegan)", "نظام غذائي: نباتي"),
    (r"بدون (.+) في كل", "قيد عام: بدون {match}"),
    (r"(حلال فقط|halal only)", "حلال فقط"),
]


def detect_constraints(message: str, session: Session) -> None:
    """
    Detect and store critical constraints (allergies, dietary restrictions) from user message.

    These constraints will be injected into all agent system prompts.
    """
    for pattern, template in CONSTRAINT_PATTERNS:
        match = re.search(pattern, message, re.IGNORECASE)
        if match:
            if match.groups():
                constraint = template.format(match=match.group(1))
            else:
                constraint = template.format(match="")
            session.add_constraint(constraint)


# Note: Dynamic prompt injection (customer name, constraints, order state)
# is handled via handoff filters which inject context as <HANDOFF_CONTEXT> blocks.
# The agent system prompts contain placeholders, but the SDK doesn't support
# per-message instruction updates. Context is passed via handoff summaries instead.


async def process_message(user_id: str, message: str) -> tuple[str, bool]:
    """
    Process a user message through the agent system.

    Args:
        user_id: Unique identifier for the user
        message: User's message in Arabic

    Returns:
        Tuple of (Agent's response, handoff_occurred)
    """
    start_time = time.time()

    # Get or create session
    session = SessionStore.get_by_user(user_id)
    is_new_session = session is None
    if not session:
        session = SessionStore.create(user_id)
        logging.info(f"[SESSION] New session created: {session.session_id}")

    SessionStore.set_current(session.session_id)

    # Detect and store constraints (allergies, etc.)
    detect_constraints(message, session)

    # Detect order intent from message (for first message that includes order)
    # Only detect safety-critical constraints (allergies) - LLM handles everything else
    _detect_safety_constraints(message, session)

    # Determine which agent should handle this message
    agent_name = _determine_current_agent(session)
    agent = AGENTS.get(agent_name, greeting_agent)

    # Log routing decision with debug info
    logging.info(f"[ROUTING] Message → {agent_name} agent")
    logging.debug(
        f"[ROUTING DEBUG] current_agent={session.current_agent}, "
        f"mode={session.order_mode}, location_confirmed={session.location_confirmed}, "
        f"address_complete={session.address_complete}, items={len(session.order_items)}"
    )

    # Build context-enriched input with conversation history
    # This ensures the agent knows what's already been collected AND what was said before
    session_context = _build_session_context_for_input(session)

    # Build input as a string with conversation history context
    # Include recent conversation history in the message itself for context
    history_context = ""
    if session.conversation_history:
        recent_history = session.conversation_history[
            -10:
        ]  # Last 5 exchanges (10 messages)
        history_lines = []
        for msg in recent_history:
            role_label = "العميل" if msg["role"] == "user" else "المطعم"
            history_lines.append(f"{role_label}: {msg['content']}")
        if history_lines:
            history_context = (
                "\n\n## المحادثة السابقة:\n" + "\n".join(history_lines) + "\n"
            )

    # Build current message with session context and history
    current_message = f"""{session_context}{history_context}

رسالة العميل الحالية: {message}"""

    # Store user message in conversation history (raw, without session context)
    # Don't store <HANDOFF_START> signals
    if "<HANDOFF_START>" not in message:
        session.conversation_history.append({"role": "user", "content": message})

    # Run agent with enriched input and logging hooks
    # max_turns=20 to handle complex multi-item orders
    handoff_occurred = False
    try:
        # Import filters
        from core.truncation_filter import truncation_filter
        
        result = await Runner.run(
            agent,
            input=current_message,  # Pass as string (SDK supports str | list)
            run_config=RunConfig(
                model_provider=provider,
                call_model_input_filter=truncation_filter,  # Truncate before LLM calls
            ),
            hooks=logging_hooks,
            max_turns=20,
        )
    except Exception as e:
        error_msg = str(e)

        # Handle max turns exceeded (complex order)
        if "Max turns" in error_msg or "MaxTurnsExceeded" in str(type(e)):
            logging.warning("[MAX TURNS] Complex order exceeded turn limit")
            # Try to save what we have
            order_summary = ""
            if session.order_items:
                items_text = ", ".join(
                    f"{i.quantity} {i.name_ar}" for i in session.order_items
                )
                order_summary = f"\n\nتم إضافة: {items_text}"
            return (
                f"عذراً، الطلب معقد جداً. حاول طلب أصناف أقل في كل مرة.{order_summary} 📝",
                False,
            )

        # Handle Gemini-specific errors (thought signatures)
        if "thought_signature" in error_msg or "Gemini models require" in error_msg:
            logging.error("[MODEL ERROR] Gemini models not compatible with SDK")
            return (
                "عذراً، هذا النموذج غير متوافق. الرجاء تغيير النموذج في config.py ⚠️",
                False,
            )

        # Handle model validation errors (malformed tool calls)
        if "validation error" in error_msg.lower() or "arguments" in error_msg:
            logging.error(
                f"[MODEL ERROR] Malformed response from model: {error_msg[:200]}"
            )
            return ("عذراً، حدث خطأ في النظام. الرجاء المحاولة مرة أخرى. 🔄", False)

        # Handle rate limits
        if "rate limit" in error_msg.lower() or "429" in error_msg:
            logging.error("[RATE LIMIT] Rate limit exceeded")
            return (
                "عذراً، النظام مشغول. الرجاء الانتظار ثم المحاولة مرة أخرى. ⏳",
                False,
            )

        raise

    duration_ms = int((time.time() - start_time) * 1000)

    # Track agent transitions (handoffs)
    final_agent = result.last_agent.name if result.last_agent else agent_name
    
    # Debug handoff logic
    logging.debug(f"[HANDOFF DEBUG] agent={agent.name}, final_agent={final_agent}, last_agent object={result.last_agent}")
    
    if final_agent != agent.name:
        handoff_occurred = True
        logging.info(f"[HANDOFF] {agent.name} → {final_agent}")
        if ENABLE_STRUCTURED_LOGS:
            structured_logger.log_handoff(
                session_id=session.session_id,
                from_agent=agent.name,
                to_agent=final_agent,
                handoff_messages=[{"role": "user", "content": message}],
                session_context={
                    "customer_name": session.customer_name,
                    "intent": session.intent,
                    "order_mode": session.order_mode,
                    "district": session.district,
                    "order_items_count": len(session.order_items),
                },
            )
    else:
        handoff_occurred = False


    # Update current agent based on where we ended up
    if result.last_agent:
        session.current_agent = result.last_agent.name.replace("_agent", "")

    # Log turn completion
    logging.info(f"[TURN COMPLETE] Agent: {final_agent}, Duration: {duration_ms}ms")

    # Store assistant response in conversation history
    if result.final_output:
        session.conversation_history.append(
            {"role": "assistant", "content": str(result.final_output)}
        )

        # Limit history to prevent token overflow (last 20 messages)
        if len(session.conversation_history) > 20:
            session.conversation_history = session.conversation_history[-20:]

        logging.debug(f"[HISTORY] Now has {len(session.conversation_history)} messages")

    return result.final_output, handoff_occurred


def _detect_safety_constraints(message: str, session: Session) -> None:
    """
    Detect safety-critical constraints (allergies, dietary restrictions).
    These are detected programmatically for safety - all other info is handled by LLM.
    """
    import re

    # Only detect allergies/constraints - safety critical
    allergy_patterns = [
        (r"حساسية\s+(?:من\s+)?(\w+)", "حساسية"),
        (r"عندي\s+حساسية", "حساسية"),
        (r"ما\s*(?:أ|ا)كل\s+(\w+)", "لا يأكل"),
        (r"بدون\s+(\w+)", "بدون"),
    ]

    for pattern, label in allergy_patterns:
        match = re.search(pattern, message, re.IGNORECASE)
        if match:
            constraint = f"{label}: {match.group(0)}"
            if constraint not in session.constraints:
                session.constraints.append(constraint)
                logging.info(f"[SAFETY] Detected constraint: {constraint}")


async def main():
    """Main console interface for testing."""
    print_rtl("مرحباً بك في مطعم البيت العربي! 🏠")
    print_rtl("(اكتب 'خروج' للإنهاء)")
    print("-" * 40)

    user_id = "console_user"
    pending_handoff = False

    while True:
        try:
            if pending_handoff:
                # Auto-drive the next turn!
                print_rtl("\n🔄 جاري تحويل المحادثة...")
                user_input = "<HANDOFF_START>"
            else:
                user_input = input("\n👤 أنت: ").strip()

            if user_input.lower() in ["خروج", "exit", "quit"] and not pending_handoff:
                print_rtl("شكراً لزيارتك! 🙏")
                break

            if not user_input:
                continue

            response, handoff_occurred = await process_message(user_id, user_input)
            
            # Update handoff state
            pending_handoff = handoff_occurred and not response
            
            # If handoff happened, response might be empty or valid
            if response:
                print_rtl(f"\n🤖 المطعم: {response}")
            
        except KeyboardInterrupt:
            print_rtl("\n\nشكراً لزيارتك! 🙏")
            break
        except Exception as e:
            print_rtl(f"\n❌ خطأ: {e}")
            import traceback

            traceback.print_exc()
            pending_handoff = False  # Reset on error


def parse_args():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Arabic Restaurant Ordering Agent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
RTL Display Options:
  --rtl standard   Use Unicode bidirectional marks (requires iTerm2 experimental RTL support)
  --rtl fallback   Reverse Arabic text for display (works in any terminal)

Examples:
  python main.py                    # Use standard RTL (default)
  python main.py --rtl fallback     # Use fallback method
  python main.py --verbose          # Show detailed logs
  python main.py --no-json-logs     # Disable JSON structured logs
  python main.py --log-file session.log # Write logs to file
        """,
    )
    parser.add_argument(
        "--rtl",
        choices=["bidi", "fallback"],
        default="bidi",
        help="RTL display method: bidi (default) or fallback",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose logging (DEBUG level)",
    )
    parser.add_argument(
        "--no-json-logs",
        action="store_true",
        help="Disable structured JSON logging (use simple console logs)",
    )
    parser.add_argument(
        "--log-file",
        type=str,
        help="Write logs to file instead of console (e.g., --log-file session.log)",
    )
    return parser.parse_args()


if __name__ == "__main__":
    import sys
    args = parse_args()
    
    # Configure logging based on args
    log_format = "[%(asctime)s] %(message)s"
    date_format = "%H:%M:%S"
    
    handlers = []
    LOG_LEVEL = "DEBUG" if args.verbose else "INFO"

    if args.log_file:
        # File logging
        file_handler = logging.FileHandler(args.log_file, mode='w', encoding='utf-8')
        file_handler.setFormatter(logging.Formatter(log_format, datefmt=date_format))
        handlers.append(file_handler)
        print(f"📝 Logging to file: {args.log_file}")
    else:
        # Console logging
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(logging.Formatter(log_format, datefmt=date_format))
        handlers.append(console_handler)
    
    logging.basicConfig(
        level=getattr(logging, LOG_LEVEL, logging.INFO),
        handlers=handlers,
        force=True
    )

    if args.verbose:
        print("Verbose logging enabled")

    # Configure JSON logs
    if args.no_json_logs:
        import sys

        current_module = sys.modules[__name__]
        current_module.ENABLE_STRUCTURED_LOGS = False
        print("JSON structured logs disabled")

    # Import RTL print function based on argument
    import sys

    current_module = sys.modules[__name__]

    if args.rtl == "fallback":
        from core.rtl_fallback import print_rtl_fallback

        current_module.print_rtl = print_rtl_fallback
        print("Using fallback RTL method (reversed Arabic text)")
    else:
        from core.rtl import print_rtl as _print_rtl

        current_module.print_rtl = _print_rtl
        print("Using standard RTL method (Unicode bidirectional marks)")
        print(
            "Note: If Arabic doesn't display correctly, try: python main.py --rtl fallback"
        )

    print()
    asyncio.run(main())
