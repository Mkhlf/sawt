"""
Terminal-based runner - uses main.py directly via pexpect.

This ensures the test uses the EXACT same code path as a real user.
"""

import asyncio
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass, field

# Check if pexpect is available
try:
    import pexpect
except ImportError:
    pexpect = None
    print("Warning: pexpect not installed. Run: pip install pexpect")

from config import OPENROUTER_API_KEY, OPENROUTER_BASE_URL
from openai import AsyncOpenAI

from .customer_llm import CustomerLLM, get_persona, CustomerPersona
from .runner import ScenarioResult, Message, ToolCall


class TerminalRunner:
    """
    Runs tests by interacting with main.py via terminal.
    
    This ensures the test uses the exact same code path as a real user,
    including all routing logic, session management, and agent handoffs.
    """
    
    def __init__(self, verbose: bool = False, timeout: int = 60):
        self.verbose = verbose
        self.timeout = timeout
        self.project_dir = Path(__file__).parent.parent.parent
    
    def _log(self, message: str):
        """Print if verbose mode is on."""
        if self.verbose:
            print(f"[TERMINAL] {message}")
    
    async def run_scenario_via_terminal(self, scenario_id: str) -> ScenarioResult:
        """
        Run a scenario by interacting with main.py directly.
        
        Args:
            scenario_id: ID of the scenario to run
            
        Returns:
            ScenarioResult with the conversation
        """
        if pexpect is None:
            raise RuntimeError("pexpect not installed. Run: pip install pexpect")
        
        persona = get_persona(scenario_id)
        if not persona:
            raise ValueError(f"No persona found for scenario: {scenario_id}")
        
        self._log(f"Running terminal scenario: {scenario_id}")
        self._log(f"  Goal: {persona.goal}")
        start_time = datetime.now()
        
        # Initialize customer LLM
        customer = CustomerLLM()
        customer.reset()
        
        messages: list[Message] = []
        error = None
        
        try:
            # Start main.py process
            cmd = f"cd {self.project_dir} && source .venv/bin/activate && python main.py --no-json-logs"
            child = pexpect.spawn("/bin/zsh", ["-c", cmd], encoding="utf-8", timeout=self.timeout)
            
            # Wait for initial prompt
            child.expect("أنت:", timeout=30)
            self._log("  Main.py started, waiting for first prompt...")
            
            # Get initial customer message
            user_message = await customer.get_initial_message(persona)
            if not user_message or len(user_message.strip()) < 3:
                user_message = "السلام عليكم، ابي اطلب برجر لحم استلام"
            
            self._log(f"  [1] Customer: {user_message[:50]}...")
            
            for turn in range(1, persona.max_turns + 1):
                # Send customer message
                child.sendline(user_message)
                
                # Wait for agent response (look for next prompt)
                try:
                    child.expect("أنت:", timeout=self.timeout)
                    
                    # Extract agent response from output
                    # Extract agent response from output
                    output = child.before
                    agent_response, tool_calls, handoff_target = self._extract_agent_response(output)
                    
                    self._log(f"  → Agent: {agent_response[:50]}..." if agent_response else "  → (no response)")
                    if handoff_target:
                        self._log(f"  ↪ [HANDOFF] -> {handoff_target}")
                    if tool_calls:
                        self._log(f"  🛠️ [TOOLS] {len(tool_calls)} calls")
                    
                    # Record messages
                    messages.append(Message(role="user", content=user_message))
                    messages.append(Message(
                        role="assistant", 
                        content=agent_response or "(no response)",
                        tool_calls=tool_calls
                    ))
                    
                    # Get next customer response
                    if turn < persona.max_turns:
                        user_message = await customer.get_response(persona, agent_response, turn + 1)
                        self._log(f"  [{turn + 1}] Customer: {user_message[:50]}...")
                    
                    if "[SESSION_END]" in output:
                        self._log("  ✅ Session end signal detected")
                        break
                        
                    # Check for ending signals - STRICTER CHECK
                    # Avoid matching "تم" (in استلام/تمام) or "خلاص" (in خلاص بس)
                    # or "شكرا" (often used politely mid-conversation)
                    lowered = user_message.lower()
                    is_farewell = any(end in lowered for end in ["مع السلامة", "وداعا", "باي"])
                    
                    if is_farewell:
                        # Send final message and get response
                        child.sendline(user_message)
                        try:
                            child.expect("أنت:", timeout=15)
                            final_output = child.before
                            final_response, final_tools, _ = self._extract_agent_response(final_output)
                            messages.append(Message(role="user", content=user_message))
                            messages.append(Message(
                                role="assistant", 
                                content=final_response or "شكرا لك!",
                                tool_calls=final_tools
                            ))
                        except pexpect.TIMEOUT:
                            pass
                        break
                            
                except pexpect.TIMEOUT:
                    self._log(f"  ⚠️ Timeout waiting for response")
                    break
                except pexpect.EOF:
                    self._log(f"  ⚠️ Process ended")
                    break
                # any other error, log it:
                except Exception as e:
                    error = str(e)
                    self._log(f"  ❌ Error: {error}")
                    break
            
            # Send exit command
            try:
                child.sendline("خروج")
                child.expect(pexpect.EOF, timeout=5)
            except:
                child.terminate()
                
        except Exception as e:
            error = str(e)
            self._log(f"  ❌ Error: {error}")
        
        # Calculate duration
        duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)
        
        # Build result (we don't have direct session access, so infer from conversation)
        final_session = self._infer_session_from_messages(messages)
        final_order = self._infer_order_from_messages(messages)
        
        return ScenarioResult(
            scenario_id=scenario_id,
            scenario_name=f"Terminal: {persona.goal[:40]}",
            messages=messages,
            final_order=final_order,
            final_session=final_session,
            duration_ms=duration_ms,
            success=error is None and len(messages) > 0,
            error=error,
        )
    
    def _extract_agent_response(self, output: str) -> tuple[str, list[ToolCall], str | None]:
        """
        Extract agent response, tool calls, and handoff info from terminal output.
        
        Returns:
            Tuple of (response_text, tool_calls_list, handoff_target)
        """
        if not output:
            return "", [], None
        
        # Split by newlines
        lines = output.strip().split("\n")
        
        response_lines = []
        tool_calls: list[ToolCall] = []
        handoff_target = None
        capture_response = False
        
        for line in lines:
            clean_line = self._clean_line(line)
            
            # Capture Tool Calls
            # Format: [INFO] [TOOL START] tool_name
            if "[TOOL START]" in clean_line:
                # Extract tool name
                match = re.search(r"\[TOOL START\] (\w+)", clean_line)
                if match:
                    tool_name = match.group(1)
                    # We don't have result/arguments from logs easily, so use placeholders
                    tool_calls.append(ToolCall(
                        name=tool_name, 
                        arguments={}, 
                        result=None
                    ))
                continue
            
            # Capture Handoffs
            # Format: [HANDOFF] agent_a -> agent_b
            if "[HANDOFF]" in clean_line:
                match = re.search(r"-> (\w+)", clean_line)
                if match:
                    handoff_target = match.group(1)
                continue

            # Skip other log lines
            if clean_line.startswith("[") and "]" in clean_line[:20]:
                continue
            
            # Skip HTTP info lines
            if "HTTP Request:" in line:
                continue

            # Skip empty lines at start
            if not capture_response and not clean_line:
                continue
            
            # Look for restaurant response marker
            if "المطعم:" in line or "🤖" in line:
                capture_response = True
                # Extract after the marker
                if ":" in line:
                    response_lines.append(line.split(":", 1)[-1].strip())
                continue
            
            if capture_response and clean_line:
                response_lines.append(clean_line)
        
        response_text = " ".join(response_lines).strip()
        
        # Fallback: Check for Python Traceback/Errors
        if not response_text and ("Traceback" in output or "Error code:" in output):
            # Capture error lines
            error_lines = [l for l in lines if "Traceback" in l or "Error" in l or "File" in l]
            response_text = "❌ SYSTEM ERROR: " + " ".join(error_lines[:3])
            
        return response_text, tool_calls, handoff_target

    def _clean_line(self, line: str) -> str:
        """Remove RTL marks and whitespace."""
        # Remove RTL/LTR/POP marks
        line = line.replace("\u202b", "").replace("\u202c", "").replace("\u202a", "")
        return line.strip()
    
    def _infer_session_from_messages(self, messages: list[Message]) -> dict:
        """Infer session state from conversation messages."""
        result = {
            "customer_name": None,
            "phone": None,
            "order_mode": None,
            "district": None,
            "order_items_count": 0,
            "order_confirmed": False,
        }
        
        for msg in messages:
            content = msg.content.lower()
            
            # Detect order mode
            if "استلام" in content:
                result["order_mode"] = "pickup"
            elif "توصيل" in content:
                result["order_mode"] = "delivery"
            
            # Detect order confirmation
            if "تم تأكيد" in content or "رقم طلبك" in content:
                result["order_confirmed"] = True
            
            # Count items added (rough estimate)
            if "تم إضافة" in content or "تمت إضافة" in content:
                result["order_items_count"] += 1
        
        return result
    
    def _infer_order_from_messages(self, messages: list[Message]) -> dict | None:
        """Infer order details from conversation messages."""
        items = []
        
        for msg in messages:
            if msg.role != "assistant":
                continue
            
            # Look for "تم إضافة" pattern
            if "تم إضافة" in msg.content or "تمت إضافة" in msg.content:
                items.append({"name_ar": "item", "quantity": 1})
        
        if items:
            return {"items": items, "subtotal": 0, "delivery_fee": 0, "total": 0}
        return None


async def main():
    """Test the terminal runner."""
    runner = TerminalRunner(verbose=True)
    result = await runner.run_scenario_via_terminal("simple_pickup")
    
    print(f"\n{'='*50}")
    print(f"Result: {'✅ Success' if result.success else '❌ Failed'}")
    print(f"Duration: {result.duration_ms}ms")
    print(f"Messages: {len(result.messages)}")
    print(f"Session: {result.final_session}")


if __name__ == "__main__":
    asyncio.run(main())
