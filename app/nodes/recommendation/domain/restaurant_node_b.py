import re
from typing import Dict, Any, List

from app.nodes.core.Base_node import BaseNode
from app.config.definitions import RESTAURANT_B_CONFIG
from app.prompts.recommendation.restaurant_b_prompt import RESTAURANT_B_PROMPT
from app.nodes.utility.json_parser import parse_json_safely
from app.schemas.restaurant_schema import RestaurantCandidate


def _slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return text[:30]


class RestaurantNodeB(BaseNode):

    def __init__(self):
        super().__init__(RESTAURANT_B_CONFIG)
        self._last_tokens: Dict[str, int] = {"prompt": 0, "completion": 0, "total": 0}

    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:

        # ── 1. EXTRACTION — même mapping que Approche A ──────────────
        semantic_query  = state.get("semantic_query") or ""
        global_keywords = state.get("global_keywords") or []

        merged_context  = state.get("merged_context") or {}
        destination     = merged_context.get("destination") or "Tunisie"
        budget_level    = merged_context.get("budget_level") or "medium"
        is_family       = merged_context.get("is_family", False)

        suggestion_mode = state.get("suggestion_mode") or "exploratory"
        max_results     = 15 if suggestion_mode == "exploratory" else 10

        # ── 2. CONSTRUCTION PROMPT ───────────────────────────────────
        prompt = RESTAURANT_B_PROMPT.format(
            destination     = destination,
            semantic_query  = semantic_query,
            global_keywords = ", ".join(global_keywords) if global_keywords else "aucun",
            budget_level    = budget_level,
            is_family       = is_family,
            max_results     = max_results,
        )

        # ── 3. APPEL LLM ─────────────────────────────────────────────
        tokens_used = {"prompt": 0, "completion": 0, "total": 0}
        raw_list    = []

        try:
            response = self.call_llm(prompt=prompt)
            content  = response.get("content", "")

            usage = response.get("usage") or {}
            tokens_used["prompt"]     = usage.get("prompt_tokens", 0)
            tokens_used["completion"] = usage.get("completion_tokens", 0)
            tokens_used["total"]      = usage.get("total_tokens", 0)
            self._last_tokens         = tokens_used

            data = parse_json_safely(content)

            if isinstance(data, dict):
                raw_list = data.get("restaurants", [])
            elif isinstance(data, list):
                raw_list = data

        except Exception as e:
            self.logger.error(f"RestaurantNodeB LLM error: {e}")
            raw_list = []

        # ── 4. ENRICHISSEMENT — ajout id + tier + source ─────────────
        enriched = []
        for i, item in enumerate(raw_list):
            if not isinstance(item, dict):
                continue
            name = item.get("name") or f"restaurant_{i}"
            item["id"]     = f"llm_{i}_{_slugify(name)}"
            item["tier"]   = "llm_generated"
            item["source"] = "groq_llm"
            enriched.append(item)

        # ── 5. VALIDATION PYDANTIC ───────────────────────────────────
        validated: List[Dict] = []
        pydantic_failures = 0

        for raw in enriched:
            try:
                candidate = RestaurantCandidate(**raw)
                validated.append(candidate.model_dump())
            except Exception as e:
                pydantic_failures += 1
                self.logger.warning(f"RestaurantCandidate skip: {e}")

        # ── 6. CONFIANCE ─────────────────────────────────────────────
        confidence = self.calculate_confidence(
            model_confidence=0.6,
            required_fields_score=1.0 if destination else 0.5,
            schema_validation_score=1.0 if pydantic_failures == 0 else 0.6,
            source_reliability_score=0.7 if validated else 0.0,
        )

        # ── 7. LOGS ──────────────────────────────────────────────────
        self.logger.info(
            f"candidates={len(validated)} | "
            f"tokens=prompt:{tokens_used['prompt']} "
            f"completion:{tokens_used['completion']} "
            f"total:{tokens_used['total']} | "
            f"pydantic_fail={pydantic_failures} | "
            f"confidence={confidence:.3f}"
        )

        # ── 8. RETOUR ────────────────────────────────────────────────
        return {
            "restaurant_candidates": validated,
        }
