#!/usr/bin/env python3
"""
Generate menu.json with 100+ items using LLM (optimized with parallel generation).
"""
import json
import os
import sys
import asyncio
import time
from pathlib import Path
from openai import AsyncOpenAI
from dotenv import load_dotenv

load_dotenv()

CATEGORY_PROMPTS = {
    "main_dishes": {
        "count": 30,
        "name_ar": "الأطباق الرئيسية",
        "prompt": """Generate 30 main dishes for "البيت العربي" restaurant.

Include:
- Traditional Saudi: كبسة، مندي، جريش، مطبق
- Gulf favorites: مجبوس، مضغوط، هريس
- Grilled: مشاوي، شيش طاووق، كباب
- Burgers: برجر لحم، برجر دجاج، برجر نباتي
- Sandwiches: سندويشات لحم، دجاج، خضار
- Pasta: باستا، معكرونة

Each item needs:
- id: "main_001", "main_002", etc.
- name_ar: Arabic name
- name_en: English name
- price: 35-85 SAR
- category: "main_dishes"
- description_ar: 1-2 sentences

Some items can have sizes: {"صغير": price, "وسط": price, "كبير": price}

Output JSON: {"items": [...]}""",
    },
    "appetizers": {
        "count": 20,
        "name_ar": "المقبلات",
        "prompt": """Generate 20 appetizers for "البيت العربي" restaurant.

Include:
- Cold: حمص، بابا غنوج، تبولة، فتوش، سلطة يونانية
- Hot: كبسة كفتة، سبرنغ رول، سمبوسة، فلافل
- Dips: جبنة، زيتون، لبنة

Each item needs:
- id: "app_001", "app_002", etc.
- name_ar: Arabic name
- name_en: English name
- price: 15-35 SAR
- category: "appetizers"
- description_ar: 1-2 sentences

Output JSON: {"items": [...]}""",
    },
    "beverages": {
        "count": 20,
        "name_ar": "المشروبات",
        "prompt": """Generate 20 beverages for "البيت العربي" restaurant.

Include:
- Hot: قهوة عربية، شاي، قهوة تركية، كابتشينو
- Cold: عصير برتقال، ليمون، فراولة، مانجو
- Soft drinks: كولا، ميرندا، سفن أب
- Traditional: عرق سوس، تمر هندي، قمر الدين

Each item needs:
- id: "bev_001", "bev_002", etc.
- name_ar: Arabic name
- name_en: English name
- price: 8-25 SAR
- category: "beverages"
- description_ar: 1-2 sentences

Many should have sizes: {"صغير": price, "وسط": price, "كبير": price}

Output JSON: {"items": [...]}""",
    },
    "desserts": {
        "count": 15,
        "name_ar": "الحلويات",
        "prompt": """Generate 15 desserts for "البيت العربي" restaurant.

Include:
- Arabic: كنافة، بقلاوة، أم علي، لقيمات
- Western: كيك، آيس كريم، براوني
- Traditional: معمول، كعك، زلابية

Each item needs:
- id: "des_001", "des_002", etc.
- name_ar: Arabic name
- name_en: English name
- price: 15-45 SAR
- category: "desserts"
- description_ar: 1-2 sentences

Output JSON: {"items": [...]}""",
    },
    "sides": {
        "count": 15,
        "name_ar": "الإضافات",
        "prompt": """Generate 15 sides/additions for "البيت العربي" restaurant.

Include:
- Salads: سلطة خضار، سلطة كول سلو، سلطة جرجير
- Rice: رز أبيض، رز معمر
- Sauces: صوص خاص، مايونيز، خردل
- Extras: بطاطس، خبز، جبنة إضافية

Each item needs:
- id: "sid_001", "sid_002", etc.
- name_ar: Arabic name
- name_en: English name
- price: 5-20 SAR
- category: "sides"
- description_ar: 1-2 sentences

Output JSON: {"items": [...]}""",
    },
}


async def generate_category_items(
    client: AsyncOpenAI, category_id: str, config: dict
) -> list:
    """Generate items for a single category."""
    start_time = time.time()
    print(f"  Generating {category_id}...", end=" ", flush=True)

    try:
        # Use gpt-oss-120b:free - it's 3.7x faster than deepseek-v3.1-nex-n1:free
        # (7.5s vs 28s per request in benchmarks)
        response = await client.chat.completions.create(
            model="openai/gpt-oss-120b:free",
            messages=[
                {
                    "role": "system",
                    "content": "You are a menu designer for Saudi restaurants. Always output valid JSON.",
                },
                {"role": "user", "content": config["prompt"]},
            ],
            response_format={"type": "json_object"},
            temperature=0.7,
            timeout=60.0,  # 60 second timeout
        )

        data = json.loads(response.choices[0].message.content)
        items = data.get("items", [])

        # Ensure all items have correct category
        for item in items:
            item["category"] = category_id

        elapsed = time.time() - start_time
        print(f"✓ {len(items)} items ({elapsed:.1f}s)")
        return items
    except Exception as e:
        elapsed = time.time() - start_time
        print(f"✗ Error: {e} ({elapsed:.1f}s)")
        return []


async def generate_menu(output_path: str = "data/menu.json"):
    """Generate menu data using LLM with parallel category generation."""
    total_start = time.time()

    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        print("Error: OPENROUTER_API_KEY not found in environment")
        sys.exit(1)

    client = AsyncOpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=api_key,
        default_headers={
            "HTTP-Referer": "https://arabic-restaurant-agent.com",
            "X-Title": "Menu Generator",
        },
    )

    print("Generating menu with parallel LLM calls...")
    print("This will be much faster than generating all items at once!\n")

    # Generate all categories in parallel
    gen_start = time.time()
    tasks = [
        generate_category_items(client, cat_id, config)
        for cat_id, config in CATEGORY_PROMPTS.items()
    ]

    results = await asyncio.gather(*tasks)
    gen_elapsed = time.time() - gen_start

    # Combine all items and deduplicate
    all_items = []
    seen_ids = set()
    seen_names_ar = set()
    duplicates_removed = 0

    for items in results:
        for item in items:
            item_id = item.get("id", "")
            name_ar = item.get("name_ar", "")

            # Skip duplicates
            if item_id in seen_ids or name_ar in seen_names_ar:
                duplicates_removed += 1
                continue

            seen_ids.add(item_id)
            seen_names_ar.add(name_ar)
            all_items.append(item)

    if duplicates_removed > 0:
        print(f"\n⚠️  Removed {duplicates_removed} duplicate items")

    # Validate counts
    categories = {}
    for item in all_items:
        cat = item["category"]
        categories[cat] = categories.get(cat, 0) + 1

    print(f"\n✓ Generated {len(all_items)} items total")
    for cat_id, config in CATEGORY_PROMPTS.items():
        count = categories.get(cat_id, 0)
        expected = config["count"]
        status = "✓" if count >= expected else "⚠"
        print(f"  {status} {cat_id}: {count}/{expected}")

    # Validate minimums
    assert len(all_items) >= 100, f"Need 100+ items, got {len(all_items)}"
    assert (
        categories.get("main_dishes", 0) >= 30
    ), f"Need 30+ main_dishes, got {categories.get('main_dishes', 0)}"
    assert (
        categories.get("appetizers", 0) >= 20
    ), f"Need 20+ appetizers, got {categories.get('appetizers', 0)}"
    assert (
        categories.get("beverages", 0) >= 20
    ), f"Need 20+ beverages, got {categories.get('beverages', 0)}"
    assert (
        categories.get("desserts", 0) >= 15
    ), f"Need 15+ desserts, got {categories.get('desserts', 0)}"
    assert (
        categories.get("sides", 0) >= 15
    ), f"Need 15+ sides, got {categories.get('sides', 0)}"

    # Build final menu structure
    menu_data = {
        "items": all_items,
        "categories": [
            {"id": cat_id, "name_ar": config["name_ar"]}
            for cat_id, config in CATEGORY_PROMPTS.items()
        ],
    }

    # Save
    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(menu_data, f, ensure_ascii=False, indent=2)

    total_elapsed = time.time() - total_start
    print(f"\n✓ Saved to {output_path}")
    print(f"\n⏱️  Performance:")
    print(f"  Generation time: {gen_elapsed:.1f}s")
    print(f"  Total time: {total_elapsed:.1f}s")


if __name__ == "__main__":
    output = sys.argv[1] if len(sys.argv) > 1 else "data/menu.json"
    asyncio.run(generate_menu(output))
