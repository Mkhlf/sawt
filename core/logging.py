"""
Structured logging for agent operations.
"""
import json
import tiktoken
from datetime import datetime
from dataclasses import dataclass, asdict


@dataclass
class LogEvent:
    timestamp: str
    session_id: str
    event_type: str  # "HANDOFF" | "TOOL_CALL" | "SESSION_TIMEOUT" | "ORDER_CONFIRMED" | "TRUNCATION"
    agent: str
    data: dict


class StructuredLogger:
    """
    Structured logging for agent operations.
    
    Per assessment requirements, we log:
    - Agent transitions with timestamp
    - Tool calls with parameters AND full response
    - Context size (token estimate) at each handoff
    - Any context truncation
    """
    def __init__(self, redact_in_prod: bool = False):
        self.encoder = tiktoken.get_encoding("o200k_base")
        self.redact_in_prod = redact_in_prod 
    
    def _count_tokens(self, text: str) -> int:
        return len(self.encoder.encode(text))
    
    def _count_message_list_tokens(self, messages: list[dict]) -> int:
        """Count tokens in the actual message list being transferred."""
        total = 0
        for msg in messages:
            content = msg.get("content", "")
            total += self._count_tokens(content)
            # Add overhead for role, etc. (~4 tokens per message)
            total += 4
        return total
    
    def log_handoff(
        self, 
        session_id: str, 
        from_agent: str, 
        to_agent: str,
        handoff_messages: list[dict],  # Actual messages after input_filter
        session_context: dict
    ):
        """
        Log agent handoff with accurate token count.
        
        Args:
            handoff_messages: The exact message list being passed to the new agent
                              (after input_filter has been applied)
            session_context: Key session variables for logging
        """
        # Count tokens on the ACTUAL message payload being transferred
        context_tokens = self._count_message_list_tokens(handoff_messages)
        
        event = LogEvent(
            timestamp=datetime.now().isoformat(),
            session_id=session_id,
            event_type="HANDOFF",
            agent=from_agent,
            data={
                "from_agent": from_agent,
                "to_agent": to_agent,
                "context_tokens": context_tokens,
                "messages_transferred": len(handoff_messages),
                "session_context": session_context  # customer_name, intent, etc.
            }
        )
        self._output(event)
    
    def log_tool_call(
        self, 
        session_id: str, 
        agent: str, 
        tool: str,
        params: dict, 
        result: dict, 
        duration_ms: int
    ):
        """
        Log tool call with FULL parameters and response.
        
        Assessment requires logging "Tool calls with parameters and response".
        In production, sensitive data can be redacted via redact_in_prod flag.
        """
        # Log full result for demo/assessment (as required)
        # Production hardening: optionally redact sensitive fields
        logged_result = self._redact_if_needed(result) if self.redact_in_prod else result
        
        event = LogEvent(
            timestamp=datetime.now().isoformat(),
            session_id=session_id,
            event_type="TOOL_CALL",
            agent=agent,
            data={
                "tool": tool,
                "params": params,
                "result": logged_result,  # Full result, not summarized
                "duration_ms": duration_ms
            }
        )
        self._output(event)
    
    def log_truncation(self, session_id: str, agent: str, original_tokens: int, truncated_tokens: int):
        """Log when conversation history is truncated."""
        event = LogEvent(
            timestamp=datetime.now().isoformat(),
            session_id=session_id,
            event_type="TRUNCATION",
            agent=agent,
            data={
                "original_tokens": original_tokens,
                "truncated_tokens": truncated_tokens,
                "tokens_removed": original_tokens - truncated_tokens
            }
        )
        self._output(event)
    
    def _redact_if_needed(self, result: dict) -> dict:
        """
        Production hardening: redact sensitive fields.
        Only used when redact_in_prod=True.
        """
        redacted = result.copy()
        sensitive_fields = ["phone", "address", "payment"]
        for field in sensitive_fields:
            if field in redacted:
                redacted[field] = "[REDACTED]"
        return redacted
    
    def _output(self, event: LogEvent):
        print(json.dumps(asdict(event), ensure_ascii=False))

