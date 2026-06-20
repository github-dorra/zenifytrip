"""
Restaurant Node — Production (Approche A retenue)

Décision architecturale (2026-06-08) :
  Approche A — Google Places API pur, zéro hallucination, TTL 72h.
  Benchmark : 6/6 PASS | avg 10 candidats | ~1.4s | $0 | 0% hallucination.

Correction architecturale (2026-06-08) :
  La distance n'est pas un signal global.
  Le mode de recherche (nearby / destination / exploratory) est déterminé
  par l'intention utilisateur, non par le type d'utilisateur (hotel_id).
"""

from typing import Dict, Any, List, Optional, Tuple

from app.nodes.core.Base_node import BaseNode, NodeConfig
from app.schemas.restaurant_schema import RestaurantCandidate
from app.services.restaurant_service import RestaurantService


# Keywords sémantiques indiquant une demande de proximité explicite
PROXIMITY_KEYWORDS = {"nearbyRestaurant", "walkingDistance", "hotelRestaurant", "aroundMe"}


class RestaurantNode(BaseNode):

    def __init__(self):
        super().__init__(
            NodeConfig(
                name="restaurant_node",
                node_type="technical",
            )
        )

    # ── STRATEGY BUILDER ─────────────────────────────────────────────

    def _build_search_strategy(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Construit la stratégie de recherche selon l'intention, la destination
        et les keywords sémantiques — jamais selon le type d'utilisateur.

        Modes :
          nearby      → user demande explicitement quelque chose de proche (hotel coords)
          destination → user cible une destination précise (text search + diversité)
          exploratory → aucune destination, aucune proximité (text search large + diversité)
        """
        merged_context  = state.get("merged_context") or {}
        global_keywords = state.get("global_keywords") or []
        profile_data    = state.get("profile_data") or {}

        destination = merged_context.get("destination")
        hotel_id    = (profile_data.get("travel_preferences") or {}).get("hotel_id")

        wants_proximity = bool(set(global_keywords) & PROXIMITY_KEYWORDS)

        # Cas 1 — proximity explicitement demandée + hotel connu
        if wants_proximity and hotel_id:
            coords = RestaurantService.get_hotel_coords(hotel_id)
            if coords:
                return {
                    "mode":              "nearby",
                    "target_query":      None,
                    "reference_coords":  coords,
                    "radius_km":         2.0,
                    "require_diversity": False,
                }

        # Cas 2 — destination explicite → découverte, variété
        if destination:
            return {
                "mode":              "destination",
                "target_query":      None,
                "reference_coords":  None,
                "radius_km":         None,
                "require_diversity": True,
            }

        # Cas 3 — exploratoire (pas de destination, pas de proximité)
        return {
            "mode":              "exploratory",
            "target_query":      None,
            "reference_coords":  None,
            "radius_km":         None,
            "require_diversity": True,
        }

    # ── RUN ──────────────────────────────────────────────────────────

    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:

        # ── 1. EXTRACTION ────────────────────────────────────────────
        semantic_query  = state.get("semantic_query") or ""
        global_keywords = state.get("global_keywords") or []

        merged_context  = state.get("merged_context") or {}
        destination     = merged_context.get("destination")
        budget_level    = merged_context.get("budget_level")
        is_family       = merged_context.get("is_family", False)

        suggestion_mode = state.get("suggestion_mode") or "exploratory"
        max_candidates  = 15 if suggestion_mode == "exploratory" else 10

        # ── 2. STRATÉGIE DE RECHERCHE ────────────────────────────────
        search_strategy = self._build_search_strategy(state)

        self.logger.info(
            f"RestaurantNode strategy: mode={search_strategy['mode']} | "
            f"destination={destination} | "
            f"proximity_kw={set(global_keywords) & PROXIMITY_KEYWORDS}"
        )

        # ── 3. APPEL SERVICE ─────────────────────────────────────────
        try:
            raw_candidates, benchmark = RestaurantService.get_restaurant_candidates(
                semantic_query=semantic_query,
                global_keywords=global_keywords,
                destination=destination,
                budget_level=budget_level,
                is_family=is_family,
                search_strategy=search_strategy,
                max_candidates=max_candidates,
            )
        except Exception as e:
            self.logger.error(f"RestaurantNode service error: {e}")
            raw_candidates, benchmark = [], {}

        # ── 4. VALIDATION PYDANTIC ───────────────────────────────────
        validated: List[Dict] = []
        pydantic_failures = 0

        for raw in raw_candidates:
            try:
                candidate = RestaurantCandidate(**raw)
                validated.append(candidate.model_dump())
            except Exception as e:
                pydantic_failures += 1
                self.logger.warning(f"RestaurantCandidate skip: {e}")

        # ── 5. CONFIANCE ─────────────────────────────────────────────
        confidence = self.calculate_confidence(
            model_confidence=0.0,
            required_fields_score=1.0 if destination else 0.5,
            schema_validation_score=1.0 if pydantic_failures == 0 else 0.6,
            source_reliability_score=1.0 if validated else 0.0,
        )

        # ── 6. LOGS ──────────────────────────────────────────────────
        self.logger.info(
            f"candidates={len(validated)} | "
            f"mode={benchmark.get('search_mode', 'none')} | "
            f"diversity={search_strategy['require_diversity']} | "
            f"api_calls={benchmark.get('api_calls_google', 0)} | "
            f"cache_hits={benchmark.get('cache_hits', 0)} | "
            f"latency_api={benchmark.get('latency_api_ms', 0)}ms | "
            f"pydantic_fail={pydantic_failures} | "
            f"confidence={confidence:.3f}"
        )

        # ── 7. RETOUR ────────────────────────────────────────────────
        return {
            "restaurant_candidates": validated,
        }
