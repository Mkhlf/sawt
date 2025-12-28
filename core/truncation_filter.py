"""
Context truncation filter for OpenAI Agents SDK.
Implements call_model_input_filter for actual context modification.
"""

import logging
import tiktoken
from typing import Any, Union
from config import CONTEXT_THRESHOLDS, MODELS


def get_encoder_for_model(model_name: str):
    """Get tiktoken encoder for a given model."""
    if "gpt-4o" in model_name or "o1" in model_name:
        return tiktoken.get_encoding("o200k_base")  # GPT-4o family
    elif "gpt-4" in model_name or "gpt-3.5" in model_name:
        return tiktoken.get_encoding("cl100k_base")  # GPT-4/3.5
    else:
        return tiktoken.get_encoding("cl100k_base")  # Default fallback


def truncation_filter(call_data) -> Any:
    """
    Filter that truncates input to stay within token limits.
    
    This is called immediately before each LLM call, allowing us to modify
    the context to stay within token limits.
    
    Args:
        call_data: CallModelData containing agent, context, and model_input
        
    Returns:
        Modified ModelInputData (or original if no truncation needed)
    """
    from agents.run import ModelInputData
    
    # Extract from CallModelData (fields: agent, context, model_data)
    agent = call_data.agent
    model_input = call_data.model_data  # Note: field is 'model_data' not 'model_input'
    
    # Get agent name without _agent suffix
    agent_key = agent.name.replace("_agent", "")
    
    # Get threshold and model for this agent
    threshold = CONTEXT_THRESHOLDS.get(agent_key, 8000)
    model_name = MODELS.get(agent_key, "openai/gpt-4o")
    encoder = get_encoder_for_model(model_name)
    
    # Count tokens in input items
    def count_tokens(items):
        total = 0
        for item in items:
            content = getattr(item, 'content', '') or ''
            if isinstance(content, str):
                total += len(encoder.encode(content))
            elif isinstance(content, list):
                # Handle list content (vision/tool results)
                for part in content:
                    if hasattr(part, 'text'):
                        total += len(encoder.encode(part.text))
        return total
    
    # Also count instructions
    instructions = model_input.instructions or ""
    instruction_tokens = len(encoder.encode(instructions))
    
    input_items = list(model_input.input) if hasattr(model_input, 'input') else []
    input_tokens = count_tokens(input_items)
    
    total_tokens = instruction_tokens + input_tokens
    
    # Check if truncation is needed
    if total_tokens <= threshold:
        return model_input  # No truncation needed
    
    # Log truncation
    logging.info(f"TRUNCATION: {agent.name} has {total_tokens} tokens (threshold: {threshold})")
    
    # Strategy: Keep system/instructions + last N messages
    # Remove older messages from the middle
    preserve_last_n = 6  # Keep last 6 messages (3 turns)
    
    if len(input_items) <= preserve_last_n:
        # Can't truncate further, return as-is
        logging.warning(f"TRUNCATION: Cannot reduce further for {agent.name}, already minimal")
        return model_input
    
    # Keep first message (often context) and last N
    truncated_items = [input_items[0]] + input_items[-preserve_last_n:]
    
    # Add summary placeholder for dropped messages
    dropped_count = len(input_items) - len(truncated_items)
    
    new_tokens = count_tokens(truncated_items) + instruction_tokens
    logging.info(f"TRUNCATION: {agent.name} reduced from {total_tokens} to {new_tokens} tokens (dropped {dropped_count} messages)")
    
    # Return modified input
    return ModelInputData(
        instructions=instructions,
        input=truncated_items
    )
