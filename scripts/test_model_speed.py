#!/usr/bin/env python3
"""
Test speed of different OpenRouter free models for menu generation.
"""
import os
import sys
import time
import asyncio
from openai import AsyncOpenAI
from dotenv import load_dotenv

load_dotenv()

MODELS = [
    "openai/gpt-oss-120b:free",
    "nex-agi/deepseek-v3.1-nex-n1:free",
    "moonshotai/kimi-k2:free",
]

TEST_PROMPT = """Generate 5 beverages for a Saudi restaurant.

Each item needs:
- id: "bev_001", "bev_002", etc.
- name_ar: Arabic name
- name_en: English name
- price: 8-25 SAR
- category: "beverages"
- description_ar: 1-2 sentences

Output JSON: {"items": [...]}"""


async def test_model(model: str, client: AsyncOpenAI):
    """Test a single model's speed."""
    print(f"\nTesting {model}...")

    try:
        start = time.time()

        response = await client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": "You are a menu designer. Always output valid JSON.",
                },
                {"role": "user", "content": TEST_PROMPT},
            ],
            response_format={"type": "json_object"},
            temperature=0.7,
        )

        elapsed = time.time() - start
        content_length = len(response.choices[0].message.content)

        print(f"  ✓ Time: {elapsed:.2f}s")
        print(f"  ✓ Output: {content_length} chars")

        return {
            "model": model,
            "time": elapsed,
            "length": content_length,
            "success": True,
        }
    except Exception as e:
        elapsed = time.time() - start
        print(f"  ✗ Error: {e} ({elapsed:.2f}s)")
        return {
            "model": model,
            "time": elapsed,
            "success": False,
            "error": str(e),
        }


async def main():
    """Test all models."""
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        print("Error: OPENROUTER_API_KEY not found")
        sys.exit(1)

    client = AsyncOpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=api_key,
        default_headers={
            "HTTP-Referer": "https://arabic-restaurant-agent.com",
            "X-Title": "Speed Test",
        },
    )

    print("=" * 60)
    print("Model Speed Test - Generating 5 beverages")
    print("=" * 60)

    results = []
    for model in MODELS:
        result = await test_model(model, client)
        results.append(result)
        await asyncio.sleep(1)  # Rate limit protection

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)

    successful = [r for r in results if r["success"]]
    if successful:
        successful.sort(key=lambda x: x["time"])

        print("\nRanking (fastest first):")
        for i, r in enumerate(successful, 1):
            print(f"{i}. {r['model']}")
            print(f"   Time: {r['time']:.2f}s")
            print(f"   Output: {r['length']} chars")

    failed = [r for r in results if not r["success"]]
    if failed:
        print("\nFailed models:")
        for r in failed:
            print(f"  ✗ {r['model']}: {r.get('error', 'Unknown error')}")


if __name__ == "__main__":
    asyncio.run(main())
