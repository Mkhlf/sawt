"""
MenuSearchEngine: Semantic-first search for menu items using FAISS and OpenAI embeddings.

Architecture:
1. Normalize menu items ONCE at index time (Arabic normalization)
2. Build TWO indexes:
   - Name-only index: For direct item name matching
   - Full index: Name + description + category for broader searches
3. Search flow:
   - Normalize query
   - Search name-only index first
   - High confidence (>0.85) → Add directly
   - Medium confidence (0.6-0.85) → Confirm with user
   - Low confidence (<0.6) → Search full index for similar/containing items
"""

import faiss
import numpy as np
from openai import OpenAI
import json
import pyarabic.araby as araby


class MenuSearchEngine:
    # Confidence thresholds (lowered - embedding similarity scores can be lower than expected)
    HIGH_CONFIDENCE = 0.75  # Add directly (was 0.80 - too strict for exact matches)
    MEDIUM_CONFIDENCE = 0.55  # Confirm with user
    # Below MEDIUM = search broader (descriptions)

    # Use the large embedding model for better accuracy
    EMBEDDING_MODEL = "openai/text-embedding-3-large"
    EMBEDDING_DIMENSIONS = (
        1024  # Large model supports up to 3072, 1024 is a good balance
    )

    def __init__(self, menu_path: str, openrouter_api_key: str):
        """Initialize with dual-index architecture."""
        self.client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=openrouter_api_key,
            default_headers={
                "HTTP-Referer": "https://arabic-restaurant-agent.com",
                "X-Title": "Menu Search",
            },
        )
        self.menu_items = self._load_menu(menu_path)

        # Build TWO separate indexes
        self.name_index, self.name_embeddings = self._build_name_index()
        self.full_index, self.full_embeddings = self._build_full_index()

    def _load_menu(self, path: str) -> list[dict]:
        """Load menu items from JSON file."""
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data["items"]

    # Phonetic groups: letters that sound similar in Arabic dialects
    # The first letter in each tuple is the "canonical" form
    PHONETIC_SIMILAR = [
        ("ج", ["ق", "ك"]),      # jeem/qaf/kaf - برقر→برجر, بركر→برجر
        ("ز", ["س", "ذ"]),      # za/seen/thal - بيتسا→بيتزا
        ("ا", ["ى"]),           # alef/alef maqsura at end
    ]
    
    # Common food-specific spelling variations (canonical: [variants])
    FOOD_SPELLING_FIXES = {
        "برجر": ["برقر", "بركر", "برغر", "بيرجر", "بورجر"],
        "بيتزا": ["بيتسا", "بيتزه", "بيتزة"],
        "شاورما": ["شورما", "شوارما", "شويرما", "شاورمه"],
        "كابتشينو": ["كبتشينو", "كابوتشينو", "كابتشينه"],
        "سندويش": ["سندوتش", "ساندويش", "سندويتش"],
        "بطاطس": ["بطاطا", "بطاطص"],
        "همبرجر": ["هامبرجر", "همبرقر", "هامبورجر", "هامبورغر"],
    }

    def _normalize_arabic(self, text: str) -> str:
        """
        Comprehensive Arabic text normalization using pyarabic.
        
        Applied to BOTH:
        - Menu items (at index time)
        - User queries (at search time)
        
        This ensures consistent representation for embedding comparison.
        """
        if not text:
            return ""

        # Remove diacritics (tashkeel) - حَمْص → حمص
        text = araby.strip_tashkeel(text)
        
        # Remove tatweel (kashida) - بـــرجر → برجر  
        text = araby.strip_tatweel(text)
        
        # Normalize Alef variations - أ إ آ ٱ → ا
        text = araby.normalize_alef(text)
        
        # Normalize Hamza variations
        text = araby.normalize_hamza(text)
        
        # Normalize Teh Marbuta - ة → ه (optional, helps with typos)
        text = araby.normalize_teh(text)
        
        # Normalize ligatures - ﻻ → لا, ﷲ → الله
        text = araby.normalize_ligature(text)
        
        return text

    def _phonetic_normalize(self, text: str) -> str:
        """
        Phonetic normalization for Arabic food terms.
        
        Handles common spelling variations that sound similar:
        - برقر → برجر (qaf sounds like jeem in dialects)
        - بيتسا → بيتزا (seen/za confusion)
        - شورما → شاورما (dialectal variation)
        
        Applied AFTER standard Arabic normalization.
        """
        if not text:
            return ""
        
        result = text
        
        # First, apply phonetic letter substitutions
        for canonical, variants in self.PHONETIC_SIMILAR:
            for variant in variants:
                result = result.replace(variant, canonical)
        
        # Then, fix known food spelling variations
        words = result.split()
        fixed_words = []
        for word in words:
            word_fixed = word
            for correct, variants in self.FOOD_SPELLING_FIXES.items():
                if word in variants:
                    word_fixed = correct
                    break
                # Also check if word contains any variant
                for variant in variants:
                    if variant in word:
                        word_fixed = word.replace(variant, correct)
                        break
            fixed_words.append(word_fixed)
        
        return " ".join(fixed_words)

    def _normalize_text(self, text: str) -> str:
        """
        Full text normalization for embedding.
        Applies Arabic normalization + phonetic normalization + basic cleanup.
        """
        if not text:
            return ""

        # Step 1: Arabic-specific normalization (pyarabic)
        text = self._normalize_arabic(text)
        
        # Step 2: Phonetic normalization (food-specific spelling fixes)
        text = self._phonetic_normalize(text)

        # Step 3: Basic cleanup
        text = " ".join(text.split())  # Remove extra whitespace
        text = text.strip().lower()
        
        return text


    def _get_embedding(self, text: str) -> np.ndarray:
        """Get embedding for normalized text. Embedding model handles typos/variations."""
        normalized = self._normalize_text(text)
        response = self.client.embeddings.create(
            model=self.EMBEDDING_MODEL,
            input=normalized,
            dimensions=self.EMBEDDING_DIMENSIONS,
        )
        return np.array(response.data[0].embedding, dtype=np.float32)

    def _batch_embed(self, texts: list[str]) -> np.ndarray:
        """Batch embed multiple texts."""
        embeddings = []
        batch_size = 100
        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            response = self.client.embeddings.create(
                model=self.EMBEDDING_MODEL,
                input=batch,
                dimensions=self.EMBEDDING_DIMENSIONS,
            )
            for item in response.data:
                embeddings.append(item.embedding)
        return np.array(embeddings, dtype=np.float32)

    def _build_name_index(self) -> tuple[faiss.IndexFlatIP, np.ndarray]:
        """
        Build index from NAMES ONLY (normalized).
        This is for direct item matching.
        """
        texts = []
        for item in self.menu_items:
            # Just the Arabic name + English name
            name_text = f"{item['name_ar']} {item.get('name_en', '')}"
            texts.append(self._normalize_text(name_text))

        embeddings = self._batch_embed(texts)
        faiss.normalize_L2(embeddings)
        index = faiss.IndexFlatIP(self.EMBEDDING_DIMENSIONS)
        index.add(embeddings)
        return index, embeddings

    def _build_full_index(self) -> tuple[faiss.IndexFlatIP, np.ndarray]:
        """
        Build index from FULL item data (name + description + category).
        This is for broader searches (similar items, ingredients).
        """
        texts = []
        for item in self.menu_items:
            full_text = (
                f"{item['name_ar']} {item.get('name_en', '')} "
                f"{item.get('description_ar', '')} {item.get('category', '')}"
            )
            texts.append(self._normalize_text(full_text))

        embeddings = self._batch_embed(texts)
        faiss.normalize_L2(embeddings)
        index = faiss.IndexFlatIP(self.EMBEDDING_DIMENSIONS)
        index.add(embeddings)
        return index, embeddings

    def _search_index(
        self, index: faiss.IndexFlatIP, query: str, top_k: int = 5
    ) -> list[tuple[float, int]]:
        """Search a specific index and return (score, idx) pairs."""
        query_embedding = self._get_embedding(query)
        faiss.normalize_L2(query_embedding.reshape(1, -1))
        scores, indices = index.search(query_embedding.reshape(1, -1), top_k)
        return list(zip(scores[0], indices[0]))
    
    def _keyword_search(self, query: str, top_k: int = 5) -> list[dict]:
        """
        Keyword-based search with weighted scoring.
        Prioritizes exact word matches over embedding similarity.
        
        Scoring:
        - Full name match: 1.0
        - All query words found in name: 0.9
        - Most query words found: 0.7-0.9
        - Partial word matches: 0.5-0.7
        """
        query_normalized = self._normalize_text(query)
        query_fixed = self._fix_arabic_spelling(query_normalized)
        query_words = set(query_fixed.split())
        
        results = []
        for idx, item in enumerate(self.menu_items):
            name_ar = self._normalize_text(item["name_ar"])
            name_en = self._normalize_text(item.get("name_en", ""))
            
            # Check for exact name match (highest priority)
            if query_fixed == name_ar or query_fixed == name_en:
                results.append((1.0, idx))
                continue
            
            # Check if query is contained in name (or vice versa)
            if query_fixed in name_ar or name_ar in query_fixed:
                # Score based on how much of the name matches
                overlap = len(query_fixed) / max(len(name_ar), 1)
                results.append((min(0.95, 0.7 + overlap * 0.25), idx))
                continue
            
            # Word-level matching
            name_words = set(name_ar.split()) | set(name_en.split())
            
            # Count matching words
            exact_matches = query_words & name_words
            if exact_matches:
                # Score based on percentage of query words matched
                match_ratio = len(exact_matches) / len(query_words)
                # Bonus for matching more words
                score = 0.5 + match_ratio * 0.4
                results.append((score, idx))
                continue
            
            # Partial word matching (substring)
            partial_matches = 0
            for qword in query_words:
                for nword in name_words:
                    if len(qword) >= 3 and (qword in nword or nword in qword):
                        partial_matches += 1
                        break
            
            if partial_matches > 0:
                score = 0.3 + (partial_matches / len(query_words)) * 0.3
                results.append((score, idx))
        
        # Sort by score descending
        results.sort(key=lambda x: x[0], reverse=True)
        
        # Format results
        formatted = []
        for score, idx in results[:top_k]:
            formatted.append(self._format_result(self.menu_items[idx], score))
        
        return formatted

    def _format_result(self, item: dict, score: float) -> dict:
        """Format a menu item for response."""
        return {
            "id": item["id"],
            "name_ar": item["name_ar"],
            "name_en": item.get("name_en", ""),
            "price": item["price"],
            "category": item["category"],
            "has_sizes": "sizes" in item,
            "score": round(float(score), 2),
        }

    def search(self, query: str, top_k: int = 5) -> dict:
        """
        Semantic search with keyword fallback.

        Flow:
        1. Normalize query (Arabic + phonetic + basic)
        2. Try embedding search FIRST (semantic similarity)
        3. If embedding fails, use keyword search as FALLBACK
        4. Return results with confidence levels and suggested action
        
        Actions:
        - "add_directly": High confidence → Add to order directly
        - "show_options": Medium/Low confidence → Show options, user picks using select_from_offered
        - "not_found": No matches → Inform user
        """
        # ===== STEP 1: Normalize query =====
        query_normalized = self._normalize_text(query)
        
        # ===== STEP 2: Embedding search (PRIMARY) =====
        name_results = self._search_index(self.name_index, query_normalized, top_k)
        best_name_score = name_results[0][0] if name_results else 0
        best_name_idx = name_results[0][1] if name_results else -1

        # ===== HIGH CONFIDENCE: Add directly =====
        if best_name_score >= self.HIGH_CONFIDENCE and best_name_idx >= 0:
            item = self.menu_items[best_name_idx]
            return {
                "found": True,
                "confidence": "high",
                "action": "add_directly",  # Default: add to order
                "count": 1,
                "items": [self._format_result(item, best_name_score)],
                "top_match": item["name_ar"],
                "instruction": f"✅ تطابق عالي! '{item['name_ar']}' (دقة {int(best_name_score*100)}%). أضفه للطلب مباشرة.",
            }

        # ===== MEDIUM CONFIDENCE: Show options, confirm with user =====
        if best_name_score >= self.MEDIUM_CONFIDENCE and best_name_idx >= 0:
            # Get top few matches for user to choose from
            results = []
            for score, idx in name_results:
                if score >= self.MEDIUM_CONFIDENCE and idx >= 0:
                    results.append(self._format_result(self.menu_items[idx], score))

            return {
                "found": True,
                "confidence": "medium",
                "action": "show_options",  # Show options, user picks with select_from_offered
                "count": len(results),
                "items": results,
                "top_match": results[0]["name_ar"] if results else None,
                "instruction": f"⚠️ عندنا خيارات مشابهة لـ'{query}'. اعرضها على العميل واسأله أي واحد يبي. استخدم store_offered_items ثم select_from_offered.",
            }

        # ===== LOW CONFIDENCE: Try broader search (descriptions) =====
        full_results = self._search_index(self.full_index, query_normalized, top_k)

        # Combine name matches with full index matches
        all_results = []
        seen_ids = set()

        # Add name matches first
        for score, idx in name_results[:3]:
            if idx >= 0 and score >= 0.3:
                result = self._format_result(self.menu_items[idx], score)
                if result["id"] not in seen_ids:
                    all_results.append(result)
                    seen_ids.add(result["id"])

        # Add full index matches
        for score, idx in full_results:
            if score >= 0.35 and idx >= 0:
                result = self._format_result(self.menu_items[idx], score)
                if result["id"] not in seen_ids:
                    all_results.append(result)
                    seen_ids.add(result["id"])

        if all_results:
            all_results.sort(key=lambda x: x["score"], reverse=True)
            return {
                "found": True,
                "confidence": "low",
                "action": "show_options",  # Show options, user picks with select_from_offered
                "count": len(all_results),
                "items": all_results[:5],
                "top_match": all_results[0]["name_ar"] if all_results else None,
                "searched_descriptions": True,
                "instruction": f"⚠️ '{query}' غير موجود بالضبط. اعرض هذه الخيارات واستخدم store_offered_items ثم select_from_offered.",
            }

        # ===== KEYWORD FALLBACK: When embedding fails completely =====
        keyword_results = self._keyword_search(query, top_k)
        
        if keyword_results:
            return {
                "found": True,
                "confidence": "low",
                "action": "show_options",  # Show options, user picks with select_from_offered
                "count": len(keyword_results),
                "items": keyword_results,
                "top_match": keyword_results[0]["name_ar"] if keyword_results else None,
                "match_type": "keyword_fallback",
                "instruction": f"⚠️ هذه الأصناف تحتوي على '{query}'. اعرضها واستخدم store_offered_items ثم select_from_offered.",
            }

        # ===== NOT FOUND =====
        return {
            "found": False,
            "confidence": "none",
            "action": "inform_not_available",
            "query": query,
            "message": f"⛔ '{query}' غير موجود في قائمتنا.",
            "instruction": "أخبر العميل أن هذا الصنف غير متوفر. لا تقترح أصناف غير مرتبطة!",
            "available_categories": self._get_category_names(),
        }

    def get_item_by_id(self, item_id: str) -> dict | None:
        """
        Get full item details by ID.

        Used by:
        - get_item_details() tool for showing full item info
        - add_to_order() tool for validating item exists and getting price
        - modify_order_item() tool for size/price lookups
        """
        for item in self.menu_items:
            if item["id"] == item_id:
                return item
        return None

    def _get_category_names(self) -> list[str]:
        """Return available category names for suggestions."""
        return list(set(item["category"] for item in self.menu_items))
