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

from rapidfuzz import fuzz

from app.config.definitions import DAY_PLANNER_CONFIG
from app.nodes.core.Base_node import BaseNode, NodeConfig
from app.nodes.utility.json_parser import parse_json_safely
from app.prompts.recommendation.day_planner_prompt import DAY_PLANNER_PROMPT
from app.schemas.day_planner_schema import ActivityType, DayPlannerOutput
from app.utils.session_memory import extract_session_signals

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Intents qui déclenchent le day planner
# ---------------------------------------------------------------------------
DAY_PLANNER_INTENTS = {"day_planning", "trip_package_recommendation"}

# Nombre max de candidats envoyés au LLM pour limiter les tokens
MAX_CANDIDATES_TO_LLM = 12

# Types de slot devant obligatoirement être traçables à un candidat réel
# (item_type "free"/"flight" ne sont jamais issus de RANKED_CANDIDATES)
_GROUNDED_ITEM_TYPES = {"hotel", "restaurant", "activity"}
# Seuil rapidfuzz pour rattacher un nom paraphrasé à son candidat d'origine
# (proche du seuil 75 déjà utilisé pour la dédup SOURCE1/SOURCE2 de activity_node)
_NAME_MATCH_THRESHOLD = 70


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

    def __init__(self):
        super().__init__(DAY_PLANNER_CONFIG)

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
        trip_position      = state.get("trip_position")   or {}
        booking_anchors    = state.get("booking_anchors") or {}
        day_skeleton       = state.get("day_skeleton")
        session_signals    = extract_session_signals(state.get("conversation_history") or [])
        language           = intent_result.get("language", "fr")

        # --- 3. Extraire les champs métier du contexte fusionné ---
        profile_data = state.get("profile_data") or {}
        constraints  = intent_result.get("constraints") or {}

        destination   = self._resolve_destination(merged_context, constraints, profile_data, availability_result)
        duration_days = self._resolve_duration(constraints, availability_result)
        start_date    = constraints.get("start_date")

        traveler_profile = self._build_traveler_profile(
            profile_data, merged_context, constraints, state.get("user_type") or "native"
        )

        self.logger.info(
            f"[DayPlanner] day={trip_position.get('day_index')}/{trip_position.get('total_days')} "
            f"(first={trip_position.get('is_first_day')}, last={trip_position.get('is_last_day')}) | "
            f"meal_plan={booking_anchors.get('meal_plan')!r} | "
            f"traveler_type={traveler_profile.get('traveler_type')}"
        )

        # --- 4. Préparer les candidats (filtre + limite tokens) ---
        candidates_for_llm = self._prepare_candidates(ranked_results, availability_result)

        # --- 5. Construire le prompt ---
        # availability_result contient trip_position/booking_anchors imbriqués (service) —
        # on les retire de la copie envoyée au LLM pour ne pas dupliquer les tokens
        availability_slim = {k: v for k, v in availability_result.items()
                             if k not in ("trip_position", "booking_anchors")}

        prompt = DAY_PLANNER_PROMPT.format(
            ranked_candidates  = json.dumps(candidates_for_llm,  ensure_ascii=False),
            destination        = destination,
            duration_days      = duration_days,
            start_date         = start_date or "null",
            traveler_profile   = json.dumps(traveler_profile,    ensure_ascii=False),
            weather_context    = json.dumps(weather_context,     ensure_ascii=False),
            availability_result= json.dumps(availability_slim,   ensure_ascii=False),
            trip_position      = json.dumps(trip_position,       ensure_ascii=False),
            booking_anchors    = json.dumps(booking_anchors,     ensure_ascii=False),
            day_skeleton       = json.dumps(day_skeleton, ensure_ascii=False, default=str) if day_skeleton else "null",
            session_signals    = json.dumps(session_signals, ensure_ascii=False),
            language           = language,
        )

        # --- 6. Appel LLM + parsing ---
        try:
            response = self.call_llm(prompt=prompt)
            raw      = response.get("content", "")
            data     = parse_json_safely(raw)
            output   = DayPlannerOutput(**data)
            output   = self._reconcile_slot_candidates(output, candidates_for_llm)

        except Exception as exc:
            logger.error("DayPlannerNode LLM error: %s", exc, exc_info=True)
            # Fallback : itinéraire minimal avec les infos disponibles
            output = self._build_fallback(destination, duration_days)

        return {"itinerary": output.model_dump()}

    # ------------------------------------------------------------------
    # Garde-fou anti-hallucination (déterministe, Python)
    # ------------------------------------------------------------------

    def _reconcile_slot_candidates(
        self,
        output: DayPlannerOutput,
        candidates_for_llm: List[Dict[str, Any]],
    ) -> DayPlannerOutput:
        """
        Le prompt demande déjà au LLM de copier name/id EXACTEMENT depuis
        RANKED_CANDIDATES pour les slots hotel/restaurant/activity — mais rien
        ne garantit qu'il le respecte (ex. observé : "Bazaar Houmt Souk" reformulé
        en "Marché traditionnel de Houmt Souk" avec candidate_id perdu, cassant
        toute traçabilité vers le vrai document).

        Garde-fou déterministe, une seule règle un seul endroit responsable
        (même doctrine que constraint_validator_node pour les exclusions dures) :
          - candidate_id valide déjà présent → nom réécrit depuis la source de
            vérité (au cas où le LLM l'aurait quand même reformulé)
          - candidate_id absent/invalide → tentative de rattachement par nom
            (rapidfuzz) vers le pool de candidats envoyés au LLM
          - aucun match suffisant → downgrade en item_type "free" plutôt que de
            laisser une place non-traçable se faire passer pour un candidat réel
        """
        by_id = {str(c["id"]): c for c in candidates_for_llm if c.get("id")}
        name_pool = [(str(c["id"]), c.get("name") or "") for c in candidates_for_llm if c.get("id")]

        for day in output.days:
            for slot in day.slots:
                if slot.item_type not in _GROUNDED_ITEM_TYPES:
                    continue

                match = by_id.get(str(slot.candidate_id)) if slot.candidate_id else None

                if not match and name_pool:
                    best_id, best_score = None, 0
                    for cid, cname in name_pool:
                        # token_set_ratio plutôt que ratio brut — un LLM paraphrase souvent
                        # le concept avec des mots différents ("marché" vs "bazaar") en ne
                        # gardant que l'ancre de lieu commune ("Houmt Souk") ; token_set_ratio
                        # capture ce chevauchement partiel, ratio brut le rate largement.
                        score = fuzz.token_set_ratio(slot.name.lower(), cname.lower())
                        if score > best_score:
                            best_id, best_score = cid, score
                    if best_score >= _NAME_MATCH_THRESHOLD:
                        match = by_id.get(best_id)

                if match:
                    if slot.name != match.get("name"):
                        logger.info(
                            "[DayPlanner] slot reconcilié : '%s' -> '%s' (candidate_id=%s)",
                            slot.name, match.get("name"), match.get("id"),
                        )
                    match_type = match.get("item_type")
                    if match_type in _GROUNDED_ITEM_TYPES and slot.item_type != match_type:
                        logger.info(
                            "[DayPlanner] item_type corrigé pour '%s' : '%s' -> '%s'",
                            match.get("name"), slot.item_type, match_type,
                        )
                        slot.item_type = ActivityType(match_type)
                    slot.name = match.get("name") or slot.name
                    slot.candidate_id = str(match.get("id"))
                    slot.ranked_score = match.get("ranked_score")
                else:
                    logger.warning(
                        "[DayPlanner] slot '%s' (type=%s) non traçable à un candidat -> downgrade en 'free'",
                        slot.name, slot.item_type,
                    )
                    slot.item_type = ActivityType.FREE
                    slot.candidate_id = None
                    slot.ranked_score = None

        return output

    # ------------------------------------------------------------------
    # Helpers privés
    # ------------------------------------------------------------------

    def _resolve_destination(
        self,
        merged_context: Dict[str, Any],
        constraints: Dict[str, Any],
        profile_data: Dict[str, Any],
        availability: Dict[str, Any],
    ) -> str:
        """
        Résolution de la destination selon 4 niveaux de priorité :
        1. merged_context (destination normalisée par context_merger —
           inclut déjà contraintes user + fallback hôtel profil)
        2. Contraintes brutes (filet de sécurité)
        3. Destination issue de l'availability_checker (hôtel en cours)
        4. Fallback "Tunisie"
        """
        dest = merged_context.get("destination")
        if dest:
            return str(dest)

        dest = constraints.get("destination")
        if dest:
            return str(dest)

        dest = availability.get("destination")
        if dest:
            return str(dest)

        # Tentative depuis le profil (hébergement actif)
        travel_prefs  = profile_data.get("travel_preferences") or {}
        accommodation = travel_prefs.get("accommodation") or {}
        hotel_name    = accommodation.get("hotel_name", "")
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
        merged_context: Dict[str, Any],
        constraints: Dict[str, Any],
        user_type: str = "native",
    ) -> Dict[str, Any]:
        """
        Profil voyageur pour le prompt — lit les valeurs DÉJÀ calculées
        (traveler_type vient du voucher via profile_builder, jamais recalculé ici).
        merged_context prime : interests accumulés multi-tour, budget fusionné.
        """
        traveller_profile = profile_data.get("traveller_profile") or {}
        tags_data         = profile_data.get("tags") or {}
        tags              = tags_data.get("tags") or []
        return {
            "user_type"    : user_type,
            "traveler_type": traveller_profile.get("traveler_type") or "solo",  # family|couple|solo — calculé depuis le voucher
            "has_partner"  : bool(traveller_profile.get("has_partner") or False),
            "child_count"  : int(traveller_profile.get("child_count") or 0),
            "baby_count"   : int(traveller_profile.get("baby_count")  or 0),
            "budget_level" : merged_context.get("budget_level") or constraints.get("budget_level") or "medium",
            "interests"    : merged_context.get("interests") or constraints.get("interests") or tags or [],
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
                # "domain" (hotel/restaurant/activity/flight) est le champ réel posé par
                # data_merger_node — "item_type"/"type" n'existent jamais sur un candidat
                # brut, ce qui faisait retomber CHAQUE candidat sur le défaut "activity"
                # (bug trouvé en testant day_planning : un restaurant reçu par le LLM
                # comme "activity", placé le matin en violation de la règle 7 du prompt).
                "item_type"           : c.get("domain") or "activity",
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