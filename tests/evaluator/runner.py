"""
Scenario runner - executes test scenarios against the agent. 

This was deprecated in favor of the terminal based runner, the dataclass were kept as they are used in the eval. 

This module simulates user conversations by sending messages
and capturing agent responses and tool calls.
"""

import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Any

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from agents import Runner, RunConfig, set_default_openai_api, set_tracing_disabled
from config import OPENROUTER_API_KEY
from core.provider import OpenRouterModelProvider
from core.session import SessionStore
from core.menu_search import MenuSearchEngine

# Initialize OpenRouter provider
set_default_openai_api("chat_completions")
set_tracing_disabled(True)
_provider = OpenRouterModelProvider(OPENROUTER_API_KEY)

# Initialize menu engine
_menu_engine = MenuSearchEngine("data/menu.json", OPENROUTER_API_KEY)


@dataclass
class ToolCall:
    """Record of a tool call during the conversation."""
    name: str
    arguments: dict
    result: Any
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class Message:
    """A message in the conversation."""
    role: str  # "user" or "assistant"
    content: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class ScenarioResult:
    """Result of running a scenario."""
    scenario_id: str
    scenario_name: str
    messages: list[Message]
    final_order: dict | None
    final_session: dict
    duration_ms: int
    success: bool
    error: str | None = None
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "scenario_id": self.scenario_id,
            "scenario_name": self.scenario_name,
            "messages": [asdict(m) for m in self.messages],
            "final_order": self.final_order,
            "final_session": self.final_session,
            "duration_ms": self.duration_ms,
            "success": self.success,
            "error": self.error,
        }

