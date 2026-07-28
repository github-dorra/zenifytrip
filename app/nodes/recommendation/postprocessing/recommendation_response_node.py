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
from app.utils.time_utils import hour_of
from app.utils.session_memory import extract_session_signals
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

# Plafond de candidats envoyés au LLM
_MAX_PER_DOMAIN = 4                      # intents mono-domaine
_MAX_BY_INTENT = {
    "day_planning":                4,    # avant : jusqu'à 16 (4 × 4 domaines)
    "trip_package_recommendation": 6,
}

# Ordre de priorité pour le score final (ranked_score = sortie ranking V2)
_SCORE_KEYS = ("ranked_score", "score", "match_score", "final_score")

# Vocabulaire NORMALISÉ par intent_classifier (contrat du prompt) → activity_type des candidats
_INTEREST_TO_ACTIVITY_TYPE = {
    "cultural_activity": "culture",
    "beach":             "nature",
    "nature":            "nature",
    "outdoor_activity":  "nature",
    "adventure":         "adventure",
    "sports":            "adventure",
    "relaxation":        "relax",
    "shopping":          "city_experience",
    "nightlife":         "city_experience",
    # "food" → géré par le domaine restaurant, pas un type d'activité
}


class RecommendationResponseNode(BaseNode):

    def __init__(self):
        super().__init__(RECOMMENDATION_RESPONSE_CONFIG)

    # =========================================================
    # HELPERS
    # =========================================================

    @staticmethod
    def _clean_candidate(candidate: Dict[str, Any]) -> Dict[str, Any]:
        """Supprime les champs internes avant envoi au LLM."""
        cleaned = {k: v for k, v in candidate.items() if k not in _INTERNAL_FIELDS and v not in (None, "", [], {})}
        if candidate.get("is_available", True) is None:
            cleaned["availability"] = "à confirmer"
        return cleaned

    @staticmethod
    def _final_score(c: Dict[str, Any]) -> float:
        for k in _SCORE_KEYS:
            v = c.get(k)
            if v is not None:
                try:
                    return float(v)
                except (TypeError, ValueError):
                    pass
        return 0.0

    @staticmethod
    def _budget_cap(budget_level: str) -> float:
        """Prix max acceptable (DT) pour ce niveau de budget."""
        return {"low": 30.0, "medium": 80.0}.get(str(budget_level).lower(), float("inf"))

    def _sort_by_budget(self, candidates: List[Dict], budget_level: str) -> List[Dict]:
        """
        Réordonne : candidats dans le budget d'abord, hors-budget en dernier.
        Ne filtre PAS — ne supprime rien — réordonne seulement.
        Inconnu (adult_price=None ou 0) → considéré comme dans le budget.
        """
        cap = self._budget_cap(budget_level)
        if cap == float("inf"):
            return candidates

        def over_budget(c: Dict) -> bool:
            price = c.get("adult_price")
            if price is None:
                return False
            try:
                return float(price) > cap
            except (TypeError, ValueError):
                return False

        return sorted(candidates, key=lambda c: (over_budget(c), -self._final_score(c)))

    @staticmethod
    def _zone_key(c: Dict[str, Any]):
        """Clé de diversité (domain, zone) — None si zone inconnue (jamais bloquant)."""
        zone = c.get("zone") or c.get("neighborhood") or c.get("hotel_zone")
        return (c.get("domain", ""), str(zone).strip().lower()) if zone else None

    def _diversify(self, items: List[Dict], cap: int) -> List[Dict]:
        """
        Max 1 candidat par (domain, zone). items doit être trié par score DESC.
        Si le plafond n'est pas atteint après diversification → complète par score
        (jamais moins de candidats à cause de la règle de diversité).
        """
        selected, leftovers, seen = [], [], set()
        for c in items:
            key = self._zone_key(c)
            if key is None or key not in seen:
                selected.append(c)
                if key:
                    seen.add(key)
            else:
                leftovers.append(c)
            if len(selected) >= cap:
                return selected
        return (selected + leftovers)[:cap]

    # =========================================================
    # SÉLECTION SLOT-DRIVEN — day_planning
    # =========================================================

    @staticmethod
    def _is_light_activity(c: Dict[str, Any]) -> bool:
        """Activité compatible demi-journée : courte, pas une excursion lourde."""
        duration = c.get("duration_hours")
        if duration is not None and float(duration) > 3:
            return False
        return c.get("activity_type") != "adventure"

    @staticmethod
    def _in_zone(c: Dict[str, Any], hotel_zone: str) -> bool:
        """Candidat dans la zone de l'hôtel (match texte souple, False si zone inconnue)."""
        if not hotel_zone:
            return False
        zone = str(c.get("zone") or c.get("neighborhood") or c.get("destination") or "").strip().lower()
        return bool(zone) and (hotel_zone in zone or zone in hotel_zone)

    @staticmethod
    def _booked_service_on_planned_day(anchors: Dict, constraints: Dict) -> bool:
        """
        True si un service hôtel booké (non annulé) tombe le jour planifié.
        Jour planifié = date EXPLICITE user sinon aujourd'hui — jamais merged.start_date
        (pollué par l'outbound_date du contrat via context_merger).
        """
        from datetime import date
        planned = str(constraints.get("start_date") or date.today().isoformat())[:10]
        for s in anchors.get("booked_services") or []:
            if str(s.get("date") or "")[:10] == planned and s.get("status") != "Cancelled":
                return True
        return False

    @staticmethod
    def _preferred_activity_types(insights: Dict, merged: Dict) -> set:
        """
        LIT les signaux déjà calculés en amont — ne recalcule rien :
          - indoor_score / outdoor_score / beach_score : weather_node
          - interests : vocabulaire normalisé par intent_classifier, mapping exact
        """
        prefer = set()

        # 1. Météo — comparaison des scores pré-calculés (jamais les flags bruts)
        indoor  = insights.get("indoor_score")
        outdoor = insights.get("outdoor_score")
        if indoor is not None and outdoor is not None:
            if indoor > outdoor:
                prefer |= {"culture", "relax", "city_experience"}
            else:
                prefer |= {"nature", "adventure"}
        if (insights.get("beach_score") or 0) >= 0.7:
            prefer.add("nature")

        # 2. Intérêts — mapping direct du vocabulaire contractuel
        for interest in (merged.get("interests") or []):
            mapped = _INTEREST_TO_ACTIVITY_TYPE.get(str(interest).strip().lower())
            if mapped:
                prefer.add(mapped)

        return prefer

    def _select_for_day_planning(self, all_candidates: List[Dict], state: Dict[str, Any]) -> List[Dict]:
        """
        Sélection contextuelle pour day_planning — pas de composition fixe.
        Précédence : filtre baby (transverse) → dernier jour → J1 tardif → J1 matinal
        → jour plein (modificateurs : avant-dernier jour, jour chaud, service booké).
        Vols toujours exclus. Hôtels exclus sauf USER NATIF multi-jours.
        """
        trip        = state.get("trip_position")   or {}
        anchors     = state.get("booking_anchors") or {}
        insights    = (state.get("weather_context") or {}).get("insights") or {}
        merged      = state.get("merged_context")  or {}
        constraints = (state.get("intent_result") or {}).get("constraints") or {}
        profile     = (state.get("profile_data") or {}).get("traveller_profile") or {}

        acts   = [c for c in all_candidates if c.get("domain") == "activity"]
        restos = [c for c in all_candidates if c.get("domain") == "restaurant"]
        hotels = [c for c in all_candidates if c.get("domain") == "hotel"]

        hotel_zone    = str(anchors.get("hotel_zone") or "").strip().lower()
        baby_on_board = int(profile.get("baby_count") or 0) > 0
        arrival_h     = hour_of(trip.get("arrival_time"))

        # ── MÉMOIRE SESSION : rejets implicites exclus du pool (avant toute branche)
        signals  = extract_session_signals(state.get("conversation_history") or [])
        rejected = set(signals["rejected_types"])
        if rejected:
            acts = [c for c in acts if c.get("activity_type") not in rejected]

        # ── CAS BABY (transverse) : filtre dur avant toute branche ──────────
        if baby_on_board:
            acts = [
                c for c in acts
                if c.get("activity_type") != "adventure"
                and not (c.get("duration_hours") is not None and float(c["duration_hours"]) > 2)
            ]

        # ── DERNIER JOUR → matinée seule ─────────────────────────────────────
        if trip.get("is_last_day"):
            light = [c for c in acts if self._is_light_activity(c)]
            light.sort(key=lambda c: (c.get("activity_type") == "city_experience",
                                      self._final_score(c)), reverse=True)
            selected = self._diversify(light, 2)
            if anchors.get("breakfast_included") is False:
                selected += restos[:1]
            return selected

        # ── J1 ARRIVÉE TARDIVE (≥ 15h) → soirée seule ───────────────────────
        if trip.get("is_first_day") and arrival_h >= 15:
            return self._diversify(restos, 2)

        # ── J1 ARRIVÉE MATINALE (< 12h) → demi-journée zone hôtel ───────────
        if trip.get("is_first_day") and 0 <= arrival_h < 12:
            near = [c for c in acts
                    if self._is_light_activity(c) and self._in_zone(c, hotel_zone)]
            pool = near or [c for c in acts if self._is_light_activity(c)]  # fallback zone inconnue
            pool.sort(key=self._final_score, reverse=True)
            selected = self._diversify(pool, 2)
            if anchors.get("lunch_included") is not True:
                selected += restos[:1]          # déjeuner seulement si non inclus
            return selected

        # ── JOUR PLEIN — modificateurs ────────────────────────────────────────
        prefer = self._preferred_activity_types(insights, merged)
        prefer |= set(signals["liked_types"])          # préférences exprimées en session

        # JOUR CHAUD → indoor (culture) doit être disponible pour le créneau 12h-16h
        # (le timing exact est appliqué par le prompt day_planner — règle EDGE CASES)
        if insights.get("is_hot_day"):
            prefer.add("culture")

        if baby_on_board:
            prefer |= {"relax", "city_experience"}

        # AVANT-DERNIER JOUR → max 1 activité longue + zone hôtel + souvenir
        is_penultimate = (
            trip.get("day_index") is not None
            and trip.get("total_days") is not None
            and trip["day_index"] == trip["total_days"] - 1
        )
        if is_penultimate:
            kept, long_seen = [], 0
            for c in sorted(acts, key=self._final_score, reverse=True):
                is_long = c.get("duration_hours") is not None and float(c["duration_hours"]) > 3
                if is_long:
                    if long_seen >= 1:
                        continue
                    long_seen += 1
                kept.append(c)
            acts = kept
            # tri : zone hôtel > souvenir (city_experience) > types préférés > score
            acts.sort(key=lambda c: (self._in_zone(c, hotel_zone),
                                     c.get("activity_type") == "city_experience",
                                     c.get("activity_type") in prefer,
                                     self._final_score(c)), reverse=True)
        else:
            acts.sort(key=lambda c: (c.get("activity_type") in prefer,
                                     self._final_score(c)), reverse=True)

        # Plafond : baby → 3 slots (rythme lent), sinon 4
        max_total = 3 if baby_on_board else 4

        # SERVICE BOOKÉ AUJOURD'HUI → un créneau est déjà pris → -1 candidat
        # (le service lui-même est ancré par le prompt day_planner via booking_anchors)
        if self._booked_service_on_planned_day(anchors, constraints):
            max_total = max(2, max_total - 1)

        # Repas inclus (AI/pension) → 1 seul resto "expérience", sinon 2
        all_meals_in = anchors.get("lunch_included") and anchors.get("dinner_included")
        n_restos = 1 if all_meals_in else min(2, max_total - 1)
        restos.sort(key=self._final_score, reverse=True)
        selected = self._diversify(acts, max_total - n_restos) + self._diversify(restos, n_restos)

        # USER NATIF multi-jours → + 1 hébergement authentique
        if state.get("user_type") == "native" and int(merged.get("duration_days") or 1) > 1 and hotels:
            selected += self._diversify(hotels, 1)

        return selected

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

        # 1. SOURCE — priorité au ranking V2 (ranked_results, déjà trié par ranked_score),
        #    fallback data_merger (candidates), fallback listes domaine brutes
        all_candidates: List[Dict] = list(
            state.get("ranked_results") or state.get("candidates") or []
        )
        if not all_candidates:
            for key in ("hotel_candidates", "flight_candidates", "restaurant_candidates", "activity_candidates"):
                all_candidates.extend(state.get(key) or [])

        # 2. TRI par score final avant toute coupe (filet de sécurité pour les fallbacks)
        all_candidates.sort(key=self._final_score, reverse=True)

        priority_domain = DOMAIN_MAP.get(primary_intent)
        cap = _MAX_BY_INTENT.get(primary_intent, _MAX_PER_DOMAIN)

        if priority_domain:
            # Intent mono-domaine : pool filtré, diversité zone, plafond
            pool = [c for c in all_candidates if c.get("domain") == priority_domain]
            selected = self._diversify(pool, cap)
        elif primary_intent == "day_planning":
            # Sélection pilotée par la situation (trip_position + ancres + météo + profil)
            selected = self._select_for_day_planning(all_candidates, state)
        else:
            # trip_package : round-robin équilibré
            # par domaine en ordre de score — garantit un mix (activité + resto + hôtel)
            by_domain: Dict[str, List] = {}
            for c in all_candidates:
                by_domain.setdefault(c.get("domain", "other"), []).append(c)
            interleaved: List[Dict] = []
            i = 0
            domain_lists = list(by_domain.values())
            while any(i < len(lst) for lst in domain_lists):
                for lst in domain_lists:
                    if i < len(lst):
                        interleaved.append(lst[i])
                i += 1
            selected = self._diversify(interleaved, cap)

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

        # Tri budget-aware : candidats dans le budget d'abord, hors-budget en dernier
        budget_level = (
            merged_context.get("budget_level")
            or (intent_result.get("constraints") or {}).get("budget_level")
            or ""
        )
        if budget_level:
            candidates = self._sort_by_budget(candidates, budget_level)

        itinerary  = state.get("itinerary")

        self.logger.info(
            f"[RecommendationResponse] intent={primary_intent} | "
            f"mode={suggestion_mode} | user_type={user_type} | "
            f"candidates={len(candidates)} | itinerary={itinerary is not None}"
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
            itinerary      = json.dumps(itinerary, ensure_ascii=False, default=str) if itinerary else "null",
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
