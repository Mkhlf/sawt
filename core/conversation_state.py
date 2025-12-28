"""
Conversation State Management.

Tracks conversation progress, prevents re-asking questions, remembers user requests,
and provides conversation memory across agent handoffs.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Set, Optional, Any
from collections import deque
from datetime import datetime


@dataclass
class ConversationState:
    """Tracks conversation progress and prevents redundant actions."""
    
    # What data has been collected
    collected_data: Dict[str, Any] = field(default_factory=dict)
    # Keys: "mode", "location", "customer_name", "phone", "items"
    
    # What questions have been asked (to prevent re-asking)
    asked_questions: Set[str] = field(default_factory=set)
    # Example: {"customer_name", "phone_number", "district"}
    
    # User's explicit requests (high priority)
    user_requests: List[Dict[str, Any]] = field(default_factory=list)
    # Example: [{"turn": 5, "type": "mode_change", "value": "pickup"}]
    
    # Recent tool call history (last 10)
    tool_history: deque = field(default_factory=lambda: deque(maxlen=10))
    # Example: deque([{"tool": "search_menu", "args": {...}, "result": {...}}])
    
    # Failed operations to retry
    failed_operations: List[Dict[str, Any]] = field(default_factory=list)
    
    # Current turn number
    turn_number: int = 0
    
    def mark_collected(self, key: str, value: Any):
        """Mark data as collected."""
        self.collected_data[key] = value
    
    def is_collected(self, key: str) -> bool:
        """Check if data already collected."""
        return key in self.collected_data and self.collected_data[key] is not None
    
    def mark_asked(self, question: str):
        """Mark question as asked."""
        self.asked_questions.add(question)
    
    def was_asked(self, question: str) -> bool:
        """Check if question was already asked."""
        return question in self.asked_questions
    
    def add_user_request(self, request_type: str, value: Any):
        """Record explicit user request."""
        self.user_requests.append({
            "turn": self.turn_number,
            "type": request_type,
            "value": value,
            "timestamp": datetime.now()
        })
    
    def get_pending_user_requests(self, request_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get unprocessed user requests."""
        if request_type:
            return [r for r in self.user_requests if r["type"] == request_type]
        return self.user_requests
    
    def clear_user_requests(self, request_type: Optional[str] = None):
        """Clear processed user requests."""
        if request_type:
            self.user_requests = [r for r in self.user_requests if r["type"] != request_type]
        else:
            self.user_requests = []
    
    def add_tool_call(self, tool_name: str, args: dict, result: Optional[dict]):
        """Record tool call in history."""
        self.tool_history.append({
            "tool": tool_name,
            "args": args,
            "result": result,
            "turn": self.turn_number,
            "success": result.get("success", True) if result else False
        })
    
    def get_recent_tool_calls(self, tool_name: Optional[str] = None, limit: int = 5) -> List[Dict[str, Any]]:
        """Get recent tool calls, optionally filtered by name."""
        calls = list(self.tool_history)
        if tool_name:
            calls = [c for c in calls if c["tool"] == tool_name]
        return calls[-limit:]
    
    def should_retry_failed_tool(self, tool_name: str) -> bool:
        """Check if tool recently failed and should be retried."""
        recent = self.get_recent_tool_calls(tool_name, limit=1)
        return len(recent) > 0 and not recent[0]["success"]
    
    def to_prompt_context(self) -> str:
        """Generate context string for agent prompts."""
        context = "\n## 🧠 CONVERSATION STATE:\n"
        
        # Collected data
        if self.collected_data:
            context += "**Already Collected (DO NOT collect again):**\n"
            for key, value in self.collected_data.items():
                if value:  # Only show non-None values
                    context += f"- {key}: {value}\n"
        
        # Asked questions
        if self.asked_questions:
            context += "\n**Already Asked (DO NOT ask again):**\n"
            for q in sorted(self.asked_questions):
                context += f"- {q}\n"
        
        # Pending user requests (CRITICAL)
        pending = self.get_pending_user_requests()
        if pending:
            context += "\n**⚠️ URGENT - User Explicit Requests (MUST HONOR):**\n"
            for req in pending[-3:]:  # Last 3 most recent
                context += f"- Turn {req['turn']}: {req['type']} → {req['value']}\n"
        
        # Recent tool calls (for debugging)
        recent_tools = list(self.tool_history)[-5:]
        if recent_tools:
            context += "\n**Recent Tool Calls (last 5):**\n"
            for t in recent_tools:
                status = "✓" if t.get("success", True) else "✗"
                args_keys = list(t.get("args", {}).keys())
                context += f"- {status} {t['tool']}({', '.join(args_keys[:3])})\n"
        
        return context
    
    def increment_turn(self):
        """Increment turn counter."""
        self.turn_number += 1


# Singleton store for conversation states
_conversation_states: Dict[str, ConversationState] = {}


def get_conversation_state(session_id: str) -> ConversationState:
    """Get or create conversation state for session."""
    if session_id not in _conversation_states:
        _conversation_states[session_id] = ConversationState()
    return _conversation_states[session_id]


def clear_conversation_state(session_id: str):
    """Clear conversation state (for testing)."""
    if session_id in _conversation_states:
        del _conversation_states[session_id]


def clear_all_conversation_states():
    """Clear all conversation states (for testing)."""
    _conversation_states.clear()
