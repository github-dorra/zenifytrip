from typing import Dict, Any, List

from app.nodes.core.Base_node import BaseNode, NodeConfig
from app.schemas.restaurant_schema import RestaurantCandidate
from app.services.restaurant_service_a import RestaurantServiceA


class RestaurantNodeA(BaseNode):

    def __init__(self):
        super().__init__(
            NodeConfig(
                name="restaurant_node_a",
                node_type="technical",
            )
        )

    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:

        # ── 1. EXTRACTION — mapping validé ───────────────────────────
        semantic_query      = state.get("semantic_query") or ""
        global_keywords     = state.get("global_keywords") or []

        merged_context  = state.get("merged_context") or {}
        destination     = merged_context.get("destination")
        budget_level    = merged_context.get("budget_level")
        is_family       = merged_context.get("is_family", False)

        profile_data    = state.get("profile_data") or {}
        hotel_id        = (profile_data.get("travel_preferences") or {}).get("hotel_id")

        suggestion_mode = state.get("suggestion_mode") or "exploratory"

        max_candidates  = 15 if suggestion_mode == "exploratory" else 10

        # ── 2. APPEL SERVICE ─────────────────────────────────────────
        try:
            raw_candidates, benchmark = RestaurantServiceA.get_restaurant_candidates(
                semantic_query=semantic_query,
                global_keywords=global_keywords,
                destination=destination,
                budget_level=budget_level,
                is_family=is_family,
                hotel_id=hotel_id,
                suggestion_mode=suggestion_mode,
                max_candidates=max_candidates,
            )
        except Exception as e:
            self.logger.error(f"RestaurantNodeA service error: {e}")
            raw_candidates, benchmark = [], {}

        # ── 3. VALIDATION PYDANTIC ───────────────────────────────────
        validated: List[Dict] = []
        pydantic_failures = 0

        for raw in raw_candidates:
            try:
                candidate = RestaurantCandidate(**raw)
                validated.append(candidate.model_dump())
            except Exception as e:
                pydantic_failures += 1
                self.logger.warning(f"RestaurantCandidate skip: {e}")

        # ── 4. CONFIANCE ─────────────────────────────────────────────
        confidence = self.calculate_confidence(
            model_confidence=0.0,
            required_fields_score=1.0 if destination else 0.5,
            schema_validation_score=1.0 if pydantic_failures == 0 else 0.6,
            source_reliability_score=1.0 if validated else 0.0,
        )

        # ── 5. LOGS ──────────────────────────────────────────────────
        self.logger.info(
            f"candidates={len(validated)} | "
            f"mode={benchmark.get('search_mode', 'none')} | "
            f"api_calls={benchmark.get('api_calls_google', 0)} | "
            f"cache_hits={benchmark.get('cache_hits', 0)} | "
            f"latency_api={benchmark.get('latency_api_ms', 0)}ms | "
            f"pydantic_fail={pydantic_failures} | "
            f"confidence={confidence:.3f}"
        )

        # ── 6. RETOUR — clé déjà dans state.py ───────────────────────
        return {
            "restaurant_candidates": validated,
        }
