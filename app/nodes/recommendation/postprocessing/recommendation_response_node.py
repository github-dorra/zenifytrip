"""
RecommendationResponseNode — Phase 4 réponse finale avec candidats
==================================================================
Reçoit les candidats fusionnés depuis data_merger et génère une réponse
conversationnelle présentant les recommandations réelles à l'utilisateur.

Chemin : data_merger → recommendation_response_node → END
(distinct de final_response_node qui gère uniquement la clarification)
"""
import json
from typing import Any, Dict, List

from app.nodes.core.Base_node import BaseNode
from app.config.definitions import RECOMMENDATION_RESPONSE_CONFIG
from app.prompts.recommendation.recommendation_response_prompt import RECOMMENDATION_RESPONSE_PROMPT
from app.schemas.reponse_schema import ResponseAgentOutput
from app.nodes.utility.json_parser import parse_json_safely

# Champs internes à masquer avant d'envoyer les candidats au LLM
_INTERNAL_FIELDS = {
    "score", "final_score", "business_score", "user_score",
    "tier", "place_id", "hotel_id", "id", "externalId",
    "long_description", "photo_url", "coordinates",
    "match_score", "is_available", "semantic_tags",
    "recommendation_context", "has_geospatial_info",
    "distance_km", "travel_time_min",
}

# Nombre max de candidats envoyés au LLM par domaine
_MAX_PER_DOMAIN = 4


class RecommendationResponseNode(BaseNode):

    def __init__(self):
        super().__init__(RECOMMENDATION_RESPONSE_CONFIG)

    # =========================================================
    # HELPERS
    # =========================================================

    @staticmethod
    def _clean_candidate(candidate: Dict[str, Any]) -> Dict[str, Any]:
        """Supprime les champs internes avant envoi au LLM."""
        return {k: v for k, v in candidate.items() if k not in _INTERNAL_FIELDS and v not in (None, "", [], {})}

    def _select_candidates(self, state: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Sélectionne les candidats pertinents selon l'intent.
        Prioritise le domaine principal, ajoute les autres en complément.
        """
        merged_context = state.get("merged_context") or {}
        primary_intent = merged_context.get("primary_intent") or ""

        DOMAIN_MAP = {
            "accommodation_recommendation": "hotel",
            "flight_recommendation":        "flight",
            "restaurant_recommendation":    "restaurant",
            "activity_recommendation":      "activity",
            "day_planning":                 None,  # tous les domaines
            "trip_package_recommendation":  None,
        }

        # Récupérer depuis data_merger (candidates fusionnés) ou domaines individuels
        all_candidates: List[Dict] = state.get("candidates") or []

        if not all_candidates:
            # Fallback : lire les candidats domaine par domaine
            for key in ("hotel_candidates", "flight_candidates", "restaurant_candidates", "activity_candidates"):
                all_candidates.extend(state.get(key) or [])

        priority_domain = DOMAIN_MAP.get(primary_intent)

        if priority_domain:
            # Domaine unique : top _MAX_PER_DOMAIN du domaine concerné
            selected = [c for c in all_candidates if c.get("domain") == priority_domain][:_MAX_PER_DOMAIN]
            # Compléter avec les autres si day_planning / package
        else:
            # Tous les domaines : top _MAX_PER_DOMAIN par domaine
            by_domain: Dict[str, List] = {}
            for c in all_candidates:
                d = c.get("domain", "other")
                by_domain.setdefault(d, []).append(c)
            selected = []
            for items in by_domain.values():
                selected.extend(items[:_MAX_PER_DOMAIN])

        return [self._clean_candidate(c) for c in selected]

    # =========================================================
    # RUN
    # =========================================================

    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:

        # ── 1. EXTRACTION ────────────────────────────────────────────
        merged_context  = state.get("merged_context") or {}
        intent_result   = state.get("intent_result")  or {}

        user_message    = state.get("normalized_message") or state.get("user_message") or ""
        primary_intent  = merged_context.get("primary_intent") or intent_result.get("primary_intent") or "unsupported"
        suggestion_mode = state.get("suggestion_mode") or "exploratory"
        user_type       = state.get("user_type") or "native"
        language        = intent_result.get("language") or "fr"

        candidates = self._select_candidates(state)

        self.logger.info(
            f"[RecommendationResponse] intent={primary_intent} | "
            f"mode={suggestion_mode} | user_type={user_type} | "
            f"candidates={len(candidates)}"
        )

        # ── 2. PROMPT ────────────────────────────────────────────────
        prompt = RECOMMENDATION_RESPONSE_PROMPT.format(
            user_message   = user_message,
            primary_intent = primary_intent,
            suggestion_mode= suggestion_mode,
            user_type      = user_type,
            language       = language,
            merged_context = json.dumps(merged_context, ensure_ascii=False, default=str),
            candidates     = json.dumps(candidates,     ensure_ascii=False, default=str),
        )

        # ── 3. APPEL LLM + PARSING ───────────────────────────────────
        raw_output = ""
        try:
            response   = self.call_llm(prompt=prompt)
            raw_output = response.get("content", "")
            parsed     = parse_json_safely(raw_output)

            if not isinstance(parsed, dict):
                raise ValueError("LLM output is not a valid JSON object")

            output = ResponseAgentOutput(**parsed)

        except Exception as e:
            self.logger.error(
                f"[RecommendationResponse] LLM error: {type(e).__name__}: {e} | raw={raw_output[:200]}"
            )
            # Fallback : réponse avec les noms disponibles ou conseil générique basé destination
            destination = merged_context.get("destination", "Tunisie")
            names = ", ".join(c.get("name", "") for c in candidates[:3] if c.get("name"))
            fallback_text = (
                f"Voici mes recommandations pour {destination} : {names} 😊"
                if names
                else f"Je vous conseille de découvrir {destination} — une destination magnifique avec de nombreuses options selon vos envies. Dites-moi vos préférences et je vous guide !"
            )
            output = ResponseAgentOutput(
                response_text=fallback_text,
                follow_up_needed=False,
                intent_handled=primary_intent,
                confidence=0.3,
                response_mode="recommendation",
            )

        # ── 4. RETOUR ────────────────────────────────────────────────
        return {
            "final_answer": output.response_text,
        }
