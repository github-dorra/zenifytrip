"""
DayPlannerNode — Phase 4
Génère un itinéraire jour/jour depuis ranked_results.
S'active uniquement pour les intents : day_planning | trip_package_recommendation.
Sinon : bypass propre → retourne {"itinerary": None}.

"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from app.nodes.core.Base_node import BaseNode, NodeConfig
from app.nodes.utility.json_parser import parse_json_safely
from app.prompts.recommendation.day_planner_prompt import DAY_PLANNER_PROMPT
from app.schemas.day_planner_schema import DayPlannerOutput

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Intents qui déclenchent le day planner
# ---------------------------------------------------------------------------
DAY_PLANNER_INTENTS = {"day_planning", "trip_package_recommendation"}

# Nombre max de candidats envoyés au LLM pour limiter les tokens
MAX_CANDIDATES_TO_LLM = 12


class DayPlannerNode(BaseNode):
    """
    Node LLM — Phase 4, Étape 14c.

    Input  (depuis GraphState) :
        ranked_results     : List[dict]  — candidats triés par ranking_node
        merged_context     : dict        — destination, duration, dates, budget, profil
        weather_context    : dict        — météo de la destination
        availability_result: dict        — trip_is_ongoing, days_remaining, booked_activity_ids
        intent_result      : dict        — primary_intent, language

    Output (vers GraphState) :
        itinerary : dict | None          — DayPlannerOutput.model_dump() ou None si bypass
    """

    def __init__(self) -> None:
        super().__init__(NodeConfig(
            name="day_planner",
            node_type="llm_agent",
            provider="groq",
            model="llama-3.3-70b-versatile",
            temperature=0.3,        # légère créativité pour varier les journées
            max_tokens=2000,        # itinéraire complet peut être long
            response_format="json",
            cache_enabled=True,
            cache_ttl_seconds=1800, # 30 min (météo + disponibilités peuvent changer)
        ))

    # ------------------------------------------------------------------
    # Méthode principale
    # ------------------------------------------------------------------

    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:

        # --- 1. Vérifier si le day planner est nécessaire ---
        intent_result   = state.get("intent_result") or {}
        primary_intent  = intent_result.get("primary_intent", "")

        if primary_intent not in DAY_PLANNER_INTENTS:
            logger.debug(
                "DayPlannerNode bypass — intent '%s' ne nécessite pas d'itinéraire.",
                primary_intent,
            )
            return {"itinerary": None}

        # --- 2. Extraire les inputs depuis le state ---
        ranked_results     = state.get("ranked_results") or []
        merged_context     = state.get("merged_context") or {}
        weather_context    = state.get("weather_context") or {}
        availability_result= state.get("availability_result") or {}
        language           = intent_result.get("language", "fr")

        # --- 3. Extraire les champs métier du contexte fusionné ---
        constraints  = merged_context.get("constraints") or {}
        profile_data = merged_context.get("profile_data") or {}
        
        if not constraints:
            constraints = intent_result.get("constraints") or {}


        destination   = self._resolve_destination(constraints, profile_data, availability_result)
        duration_days = self._resolve_duration(constraints, availability_result)
        start_date    = constraints.get("start_date")

        traveler_profile = self._build_traveler_profile(profile_data, constraints)

        # --- 4. Préparer les candidats (filtre + limite tokens) ---
        candidates_for_llm = self._prepare_candidates(ranked_results, availability_result)

        # --- 5. Construire le prompt ---
        prompt = DAY_PLANNER_PROMPT.format(
            ranked_candidates  = json.dumps(candidates_for_llm,  ensure_ascii=False),
            destination        = destination,
            duration_days      = duration_days,
            start_date         = start_date or "null",
            traveler_profile   = json.dumps(traveler_profile,    ensure_ascii=False),
            weather_context    = json.dumps(weather_context,     ensure_ascii=False),
            availability_result= json.dumps(availability_result, ensure_ascii=False),
            language           = language,
        )

        # --- 6. Appel LLM + parsing ---
        try:
            response = self.call_llm(prompt=prompt)
            raw      = response.get("content", "")
            data     = parse_json_safely(raw)
            output   = DayPlannerOutput(**data)

        except Exception as exc:
            logger.error("DayPlannerNode LLM error: %s", exc, exc_info=True)
            # Fallback : itinéraire minimal avec les infos disponibles
            output = self._build_fallback(destination, duration_days)

        return {"itinerary": output.model_dump()}

    # ------------------------------------------------------------------
    # Helpers privés
    # ------------------------------------------------------------------

    def _resolve_destination(
        self,
        constraints: Dict[str, Any],
        profile_data: Dict[str, Any],
        availability: Dict[str, Any],
    ) -> str:
        """
        Résolution de la destination selon 3 niveaux de priorité :
        1. Contraintes utilisateur (ce qu'il a demandé explicitement)
        2. Destination issue de l'availability_checker (hôtel en cours)
        3. Fallback "Tunisie"
        """
        dest = constraints.get("destination")
        if dest:
            return str(dest)

        dest = availability.get("destination")
        if dest:
            return str(dest)

        # Tentative depuis le profil (hébergement actif)
        accommodations = profile_data.get("accommodations") or []
        if accommodations:
            hotel = accommodations[0].get("hotel") or {}
            hotel_name = hotel.get("name", "")
            if hotel_name:
                return hotel_name

        return "Tunisie"

    def _resolve_duration(
        self,
        constraints: Dict[str, Any],
        availability: Dict[str, Any],
    ) -> int:
        """
        Résolution de la durée en jours :
        - Si trip_is_ongoing → days_remaining
        - Sinon → duration_days des contraintes ou 1 par défaut
        """
        if availability.get("trip_is_ongoing"):
            days_rem = availability.get("days_remaining")
            if days_rem is not None:
                try:
                    return max(1, int(days_rem))
                except (TypeError, ValueError):
                    pass

        duration = constraints.get("duration_days")
        if duration:
            try:
                return max(1, int(duration))
            except (TypeError, ValueError):
                pass

        return 1

    def _build_traveler_profile(
        self,
        profile_data: Dict[str, Any],
        constraints: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Construit un profil voyageur synthétique pour le prompt."""
        return {
            "user_type"   : profile_data.get("user_type") or "native",
            "has_partner" : bool(profile_data.get("hasPartner") or False),
            "child_count" : int(profile_data.get("childCount") or 0),
            "budget_level": constraints.get("budget_level") or "medium",
            "interests"   : constraints.get("interests") or profile_data.get("tags") or [],
        }

    def _prepare_candidates(
        self,
        ranked_results: List[Dict[str, Any]],
        availability: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """
        Filtre les candidats déjà réservés et limite le volume envoyé au LLM.
        Ne garde que les champs utiles pour réduire les tokens.
        """
        booked_ids: set = set(availability.get("booked_activity_ids") or [])

        filtered = [
            c for c in ranked_results
            if str(c.get("id", "")) not in booked_ids
        ]

        # Garder uniquement les champs pertinents pour le prompt
        slim = []
        for c in filtered[:MAX_CANDIDATES_TO_LLM]:
            slim.append({
                "id"                  : c.get("id"),
                "name"                : c.get("name"),
                "item_type"           : c.get("item_type") or c.get("type", "activity"),
                "location"            : c.get("address") or c.get("location"),
                "ranked_score"        : c.get("ranked_score"),
                "rank"                : c.get("rank"),
                "price_level"         : c.get("price_level"),
                "recommendation_reason": c.get("recommendation_reason"),
                "tier"                : c.get("tier"),
            })

        return slim

    def _build_fallback(self, destination: str, duration_days: int) -> DayPlannerOutput:
        """
        Itinéraire de secours minimal si le LLM échoue.
        Retourne un itinéraire vide avec confidence basse.
        """
        logger.warning("DayPlannerNode utilise le fallback pour '%s'.", destination)
        return DayPlannerOutput(
            destination   = destination,
            duration_days = duration_days,
            days          = [],
            weather_note  = None,
            budget_note   = None,
            travel_tips   = None,
            confidence    = 0.0,
        )