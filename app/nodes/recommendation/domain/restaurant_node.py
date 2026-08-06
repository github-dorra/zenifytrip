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

from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple

from app.nodes.core.Base_node import BaseNode, NodeConfig
from app.schemas.restaurant_schema import RestaurantCandidate
from app.services.restaurant_service import RestaurantService


# Keywords sémantiques indiquant une demande de proximité explicite
PROXIMITY_KEYWORDS = {"nearbyRestaurant", "walkingDistance", "hotelRestaurant", "aroundMe"}


class RestaurantNode(BaseNode):

    # Créneau -> establishment_types (filtre dur Atlas Search, cf. mongo_restaurant_service.py)
    _SLOT_TO_TYPES = {
        "matin": ["cafe", "dessert"],
        "midi":  ["restaurant", "fast_food", "pizzeria"],
        "soir":  ["restaurant", "bar", "fast_food", "pizzeria"],
        "snack": ["fast_food", "dessert"],
    }

    # Préférence libre (restaurant_preferences, texte extrait par intent_classifier)
    # -> establishment_types canoniques de restaurant_collection (7 valeurs, 100% remplies).
    # Rule-based, jamais deviné par un LLM — même doctrine que l'enrichissement
    # semantique d'activities_collection (Phase 5).
    _PREFERENCE_TO_ESTABLISHMENT_TYPE = {
        "pizza": ["pizzeria"], "pizzeria": ["pizzeria"], "pizzas": ["pizzeria"],
        "cafe": ["cafe"], "café": ["cafe"], "coffee": ["cafe"],
        "dessert": ["dessert"], "desserts": ["dessert"],
        "patisserie": ["dessert"], "pâtisserie": ["dessert"], "sweet": ["dessert"],
        "bbq": ["bbq"], "barbecue": ["bbq"], "grill": ["bbq"],
        "fastfood": ["fast_food"], "fast_food": ["fast_food"], "fast-food": ["fast_food"],
        "burger": ["fast_food"], "burgers": ["fast_food"],
        "bar": ["bar"], "pub": ["bar"],
    }

    def __init__(self):
        super().__init__(
            NodeConfig(
                name="restaurant_node",
                node_type="technical",
            )
        )

    # ── CRÉNEAU HORAIRE ──────────────────────────────────────────────

    @staticmethod
    def _current_time_slot() -> str:
        """Créneau depuis l'heure serveur actuelle — 4 tranches horaires."""
        h = datetime.now().hour
        if 6 <= h < 11:  return "matin"
        if 11 <= h < 15: return "midi"
        if 15 <= h < 18: return "snack"
        return "soir"

    @classmethod
    def _establishment_types_from_preferences(cls, preferences: List[str]) -> Optional[List[str]]:
        """Mappe les préférences connues (ex. 'pizza') vers establishment_types. None si aucun match connu — jamais de devinette."""
        types: List[str] = []
        for pref in preferences:
            mapped = cls._PREFERENCE_TO_ESTABLISHMENT_TYPE.get(str(pref).strip().lower())
            if mapped:
                types.extend(mapped)
        return list(dict.fromkeys(types)) or None

    def _resolve_establishment_types(
        self, state: Dict[str, Any], merged_context: Dict[str, Any]
    ) -> Optional[List[str]]:
        """
        Priorité :
          1. Préférence explicite voyageur (mappée en type connu, ex. "pizza" → pizzeria)
          2. meal_slot imposé par l'orchestrateur (chemin LLM, ex. lunch seul en HB)
          3. day_skeleton (pool complet nécessaire pour sélection slot-driven en aval)
          4. Heure courante (seulement si une date de séjour est fournie)
        """
        constraints  = (state.get("intent_result") or {}).get("constraints") or {}
        day_skeleton = state.get("day_skeleton")

        # 1. Préférence explicite — priorité absolue
        restaurant_preferences = merged_context.get("restaurant_preferences") or []
        if restaurant_preferences:
            return self._establishment_types_from_preferences(restaurant_preferences)

        # 2. Contrainte orchestrateur (meal_slot = "midi" ou "soir" ou "matin")
        orch_meal_slot = (
            (state.get("orchestrator_constraints") or {})
            .get("restaurant_node", {})
            .get("meal_slot")
        )
        if orch_meal_slot:
            # Mapper meal_slot → _SLOT_TO_TYPES (FR key)
            _MEAL_TO_SLOT = {"lunch": "midi", "dinner": "soir", "breakfast": "matin", "any": None}
            slot_key = _MEAL_TO_SLOT.get(str(orch_meal_slot).lower(), orch_meal_slot.lower())
            if slot_key and slot_key in self._SLOT_TO_TYPES:
                return self._SLOT_TO_TYPES[slot_key]

        # 3. day_skeleton → pool complet nécessaire
        if day_skeleton:
            # Demande multi-créneaux (day_planning) — le pool complet doit
            # rester disponible pour la sélection slot-driven en aval.
            return None

        if constraints.get("start_date"):
            time_slot = self._current_time_slot()
            return self._SLOT_TO_TYPES.get(time_slot)

        return None

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
        establishment_types = self._resolve_establishment_types(state, merged_context)

        # Cas 1 — proximity explicitement demandée + hotel connu
        if wants_proximity and hotel_id:
            coords = RestaurantService.get_hotel_coords(hotel_id)
            if coords:
                return {
                    "mode":                "nearby",
                    "target_query":        None,
                    "reference_coords":    coords,
                    "radius_km":           2.0,
                    "require_diversity":   False,
                    "establishment_types": establishment_types,
                }

        # Cas 2 — destination explicite → découverte, variété
        if destination:
            return {
                "mode":                "destination",
                "target_query":        None,
                "reference_coords":    None,
                "radius_km":           None,
                "require_diversity":   True,
                "establishment_types": establishment_types,
            }

        # Cas 3 — exploratoire (pas de destination, pas de proximité)
        return {
            "mode":                "exploratory",
            "target_query":        None,
            "reference_coords":    None,
            "radius_km":           None,
            "require_diversity":   True,
            "establishment_types": establishment_types,
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

        # Préférences explicites (ex. "pizza") — extraites en champ structuré par
        # intent_classifier, jamais lues par semantic_node : sans ce merge elles
        # n'atteignaient jamais la recherche (bug identifié 2026-07-28).
        restaurant_preferences = merged_context.get("restaurant_preferences") or []
        search_keywords = list(dict.fromkeys([*global_keywords, *restaurant_preferences]))

        # Filtre dur halal : détecté sur l'union des keywords + préférences.
        # Exclut les bars purs (non halal par définition), préserve les docs
        # avec type restaurant/cafe même s'ils ont aussi "bar" dans leurs types.
        halal_required = any("halal" in kw.lower() for kw in search_keywords)

        suggestion_mode = state.get("suggestion_mode") or "exploratory"
        max_candidates  = 15 if suggestion_mode == "exploratory" else 10

        # ── 2. STRATÉGIE DE RECHERCHE ────────────────────────────────
        search_strategy = self._build_search_strategy(state)

        # request_hour — transmis à MongoRestaurantService pour le scoring "hours".
        # Désactivé si day_skeleton présent : le day_planner a besoin du pool complet
        # (tous créneaux) pour sa sélection slot-driven — on ne filtre pas par heure courante.
        if not state.get("day_skeleton"):
            search_strategy["request_hour"] = datetime.now().hour

        self.logger.info(
            f"RestaurantNode strategy: mode={search_strategy['mode']} | "
            f"destination={destination} | "
            f"proximity_kw={set(global_keywords) & PROXIMITY_KEYWORDS} | "
            f"establishment_types={search_strategy.get('establishment_types')}"
        )

        # ── 3. APPEL SERVICE ─────────────────────────────────────────
        try:
            raw_candidates, benchmark = RestaurantService.get_restaurant_candidates(
                semantic_query=semantic_query,
                global_keywords=search_keywords,
                destination=destination,
                budget_level=budget_level,
                is_family=is_family,
                search_strategy=search_strategy,
                max_candidates=max_candidates,
                halal_required=halal_required,
                request_hour=search_strategy.get("request_hour"),
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
