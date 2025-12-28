"""
LLM Judge - evaluates agent interactions using strong LLMs.

Uses multiple LLM models to score agent performance on various criteria.
"""

import json
import asyncio
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Any
from openai import AsyncOpenAI

from .runner import ScenarioResult, Message


# Judge models available via OpenRouter (2025 latest versions)
JUDGE_MODELS = {
    "gpt-5.2": "openai/gpt-5.2",
    "gpt-4o": "openai/gpt-4o",  # Fallback
    
    "claude-4.5-opus": "anthropic/claude-opus-4.5",
    "gemini-3-flash": "google/gemini-3-flash-preview",
    
    "gemini-3-pro": "google/gemini-3-pro-preview",

    "kimi-k2": "moonshotai/kimi-k2-thinking"
}

DEFAULT_JUDGES = ["gpt-4o"]#, "claude-4.5-opus", "gemini-3-pro", "kimi-k2"]


@dataclass
class ScoreCard:
    """Scores from a single judge."""
    task_completion: int  # 0-10: Did the order complete correctly?
    efficiency: int  # 0-10: No unnecessary steps?
    correctness: int  # 0-10: Right items, quantities, prices?
    arabic_quality: int  # 0-10: Natural Gulf dialect?
    error_handling: int  # 0-10: Graceful handling of issues?
    comments: str  # Free-form feedback
    
    @property
    def average(self) -> float:
        """Calculate average score."""
        return (
            self.task_completion + 
            self.efficiency + 
            self.correctness + 
            self.arabic_quality + 
            self.error_handling
        ) / 5


@dataclass
class JudgeResult:
    """Result from a single judge."""
    model: str
    scores: ScoreCard
    raw_response: str
    timestamp: str
    
    def to_dict(self) -> dict:
        return {
            "model": self.model,
            "scores": asdict(self.scores),
            "average_score": self.scores.average,
            "raw_response": self.raw_response,
            "timestamp": self.timestamp,
        }


@dataclass
class EvaluationResult:
    """Complete evaluation result with all judges."""
    scenario_id: str
    scenario_name: str
    judge_results: list[JudgeResult]
    average_score: float
    
    def to_dict(self) -> dict:
        return {
            "scenario_id": self.scenario_id,
            "scenario_name": self.scenario_name,
            "judge_results": [jr.to_dict() for jr in self.judge_results],
            "average_score": self.average_score,
        }


JUDGE_PROMPT = '''You are an expert evaluator for a Saudi Arabian restaurant ordering AI assistant.

Your task is to evaluate the quality of the AI's responses in a conversation with a customer.

## Evaluation Criteria (Score 0-10 for each)

### 1. Task Completion
- Did the order complete successfully?
- Were all requested items added?
- Was the customer's intent fulfilled?

### 2. Efficiency  
- Did the AI avoid unnecessary tool calls?
- Did it process multiple items efficiently?
- Did it avoid repeating itself?

### 3. Correctness
- Were the right items identified and added?
- Were quantities correct?
- Were prices accurate?
- Was the order mode (pickup/delivery) handled correctly?

### 4. Arabic Quality
- Is the Arabic natural and fluent?
- Is it using Gulf/Saudi dialect appropriately?
- Are the responses friendly and professional?
- Are there any awkward translations or unnatural phrases?

### 5. Error Handling
- How well did it handle unavailable items?
- Did it recover from misunderstandings?
- Did it provide helpful alternatives when needed?

## Conversation to Evaluate

{conversation}

## Final Session State

{final_state}

## Expected Outcomes

{expected_outcomes}

## Your Evaluation

Respond with a JSON object in this exact format:
```json
{{
  "task_completion": <0-10>,
  "efficiency": <0-10>,
  "correctness": <0-10>,
  "arabic_quality": <0-10>,
  "error_handling": <0-10>,
  "comments": "<brief explanation of scores and any issues found>"
}}
```

Be critical but fair. Score based on actual performance, not potential.
'''


class LLMJudge:
    """Evaluates agent interactions using LLM judges."""
    
    def __init__(self, api_key: str, judges: list[str] = None):
        """
        Initialize judge with OpenRouter API key.
        
        Args:
            api_key: OpenRouter API key
            judges: List of judge model names to use
        """
        self.client = AsyncOpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=api_key,
            default_headers={
                "HTTP-Referer": "https://arabic-restaurant-agent.com",
                "X-Title": "Agent Evaluator",
            },
        )
        self.judges = judges or DEFAULT_JUDGES
    
    def _format_conversation(self, messages: list[Message]) -> str:
        """Format messages for the judge prompt."""
        lines = []
        for msg in messages:
            role = "👤 Customer" if msg.role == "user" else "🤖 Agent"
            lines.append(f"{role}: {msg.content}")
            if msg.tool_calls:
                for tc in msg.tool_calls:
                    lines.append(f"  [Tool: {tc.name}({tc.arguments})]")
        return "\n".join(lines)
    
    def _parse_scores(self, response: str) -> ScoreCard | None:
        """Parse JSON scores from judge response."""
        try:
            # Try to extract JSON from response
            json_start = response.find("{")
            json_end = response.rfind("}") + 1
            if json_start >= 0 and json_end > json_start:
                json_str = response[json_start:json_end]
                data = json.loads(json_str)
                return ScoreCard(
                    task_completion=int(data.get("task_completion", 5)),
                    efficiency=int(data.get("efficiency", 5)),
                    correctness=int(data.get("correctness", 5)),
                    arabic_quality=int(data.get("arabic_quality", 5)),
                    error_handling=int(data.get("error_handling", 5)),
                    comments=data.get("comments", ""),
                )
        except (json.JSONDecodeError, KeyError, ValueError):
            pass
        return None
    
    async def _judge_with_model(
        self, 
        model_name: str,
        scenario_result: ScenarioResult,
        expected_outcomes: dict,
    ) -> JudgeResult | None:
        """Get evaluation from a single judge model."""
        model_id = JUDGE_MODELS.get(model_name)
        if not model_id:
            return None
        
        # Format the prompt
        conversation = self._format_conversation(scenario_result.messages)
        final_state = json.dumps(scenario_result.final_session, ensure_ascii=False, indent=2)
        expected = json.dumps(expected_outcomes, ensure_ascii=False, indent=2)
        
        prompt = JUDGE_PROMPT.format(
            conversation=conversation,
            final_state=final_state,
            expected_outcomes=expected,
        )
        
        try:
            response = await self.client.chat.completions.create(
                model=model_id,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=1000,
                temperature=0.3,
            )
            
            response_text = response.choices[0].message.content
            scores = self._parse_scores(response_text)
            
            if scores:
                return JudgeResult(
                    model=model_name,
                    scores=scores,
                    raw_response=response_text,
                    timestamp=datetime.now().isoformat(),
                )
        except Exception as e:
            print(f"Judge {model_name} failed: {e}")
            
        return None
    
    async def evaluate(
        self,
        scenario_result: ScenarioResult,
        expected_outcomes: dict,
    ) -> EvaluationResult:
        """
        Evaluate a scenario result using all configured judges.
        
        Args:
            scenario_result: Result from running a scenario
            expected_outcomes: What we expected to happen
            
        Returns:
            EvaluationResult with scores from all judges
        """
        # Run all judges in parallel
        tasks = [
            self._judge_with_model(judge, scenario_result, expected_outcomes)
            for judge in self.judges
        ]
        
        results = await asyncio.gather(*tasks)
        judge_results = [r for r in results if r is not None]
        
        # Calculate average across all judges
        if judge_results:
            avg_score = sum(jr.scores.average for jr in judge_results) / len(judge_results)
        else:
            avg_score = 0.0
        
        return EvaluationResult(
            scenario_id=scenario_result.scenario_id,
            scenario_name=scenario_result.scenario_name,
            judge_results=judge_results,
            average_score=avg_score,
        )


async def main():
    """Test the judge with a mock scenario result."""
    import os
    
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        print("Set OPENROUTER_API_KEY environment variable")
        return
    
    # Create a mock scenario result for testing
    from .runner import Message
    mock_result = ScenarioResult(
        scenario_id="test",
        scenario_name="Test Scenario",
        messages=[
            Message(role="user", content="السلام عليكم ابي برجر"),
            Message(role="assistant", content="أهلاً! عندنا برجر لحم بالجبن وبرجر دجاج مشوي. أي واحد تبي؟"),
            Message(role="user", content="لحم"),
            Message(role="assistant", content="تم إضافة برجر لحم بالجبن! شي ثاني؟"),
        ],
        final_order={"items": [{"name_ar": "برجر لحم بالجبن", "quantity": 1}]},
        final_session={"order_mode": "pickup", "customer_name": None},
        duration_ms=5000,
        success=True,
    )
    
    judge = LLMJudge(api_key, judges=["gpt-4o"])
    result = await judge.evaluate(
        mock_result,
        expected_outcomes={"has_items": True},
    )
    
    print(f"Evaluation Result:")
    print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
