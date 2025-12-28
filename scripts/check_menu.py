#!/usr/bin/env python3
"""
Check menu.json for duplicates and other issues.
"""
import json
from pathlib import Path
from collections import Counter


def check_menu(menu_path: str = "data/menu.json"):
    """Analyze menu for duplicates and issues."""
    with open(menu_path, "r", encoding="utf-8") as f:
        menu = json.load(f)

    items = menu["items"]
    print(f"Total items: {len(items)}\n")

    # Check duplicate IDs
    ids = [item["id"] for item in items]
    id_counts = Counter(ids)
    duplicates = {id: count for id, count in id_counts.items() if count > 1}

    if duplicates:
        print("❌ DUPLICATE IDs FOUND:")
        for id, count in duplicates.items():
            print(f"  {id}: {count} times")
    else:
        print("✓ No duplicate IDs")

    # Check duplicate names (Arabic)
    names_ar = [item["name_ar"] for item in items]
    name_counts = Counter(names_ar)
    dup_names = {name: count for name, count in name_counts.items() if count > 1}

    if dup_names:
        print("\n⚠️  DUPLICATE NAMES (Arabic):")
        for name, count in dup_names.items():
            print(f"  {name}: {count} times")
    else:
        print("✓ No duplicate names (Arabic)")

    # Check duplicate names (English)
    names_en = [item.get("name_en", "") for item in items]
    name_en_counts = Counter(names_en)
    dup_names_en = {
        name: count for name, count in name_en_counts.items() if count > 1 and name
    }

    if dup_names_en:
        print("\n⚠️  DUPLICATE NAMES (English):")
        for name, count in dup_names_en.items():
            print(f"  {name}: {count} times")
    else:
        print("✓ No duplicate names (English)")

    # Category breakdown
    categories = {}
    for item in items:
        cat = item["category"]
        categories[cat] = categories.get(cat, 0) + 1

    print("\nCategory breakdown:")
    for cat, count in sorted(categories.items()):
        print(f"  {cat}: {count}")

    # Check required fields
    print("\nField validation:")
    required_fields = [
        "id",
        "name_ar",
        "name_en",
        "price",
        "category",
        "description_ar",
    ]
    missing_fields = []

    for i, item in enumerate(items):
        for field in required_fields:
            if field not in item:
                missing_fields.append(
                    f"Item {i} ({item.get('id', 'unknown')}): missing {field}"
                )

    if missing_fields:
        print("❌ Missing fields:")
        for msg in missing_fields[:10]:  # Show first 10
            print(f"  {msg}")
        if len(missing_fields) > 10:
            print(f"  ... and {len(missing_fields) - 10} more")
    else:
        print("✓ All items have required fields")

    return {
        "total": len(items),
        "duplicate_ids": len(duplicates),
        "duplicate_names": len(dup_names),
        "missing_fields": len(missing_fields),
    }


if __name__ == "__main__":
    check_menu()
