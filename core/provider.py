"""
OpenRouter model provider for OpenAI Agents SDK.
"""

from openai import AsyncOpenAI
from agents import Model, ModelProvider, OpenAIChatCompletionsModel


class OpenRouterModelProvider(ModelProvider):
    """
    Custom model provider for OpenRouter.

    Uses free tier models optimized for speed and quality:
    - gpt-oss-120b:free for fast routing/validation (~7.5s)
    - deepseek-v3.1-nex-n1:free for complex tool use (~28s)
    """

    def __init__(self, api_key: str):
        self.client = AsyncOpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=api_key,
            default_headers={
                "HTTP-Referer": "https://arabic-restaurant-agent.com",
                "X-Title": "Arabic Restaurant Agent",
            },
        )

    def get_model(self, model_name: str | None) -> Model:
        # Default to fastest free model (3.7x faster than deepseek)
        model = model_name or "openai/gpt-oss-120b:free"
        return OpenAIChatCompletionsModel(model=model, openai_client=self.client)
