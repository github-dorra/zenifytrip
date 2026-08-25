import operator
from typing import TypedDict, Annotated, List, Dict, Any, Optional


class GraphState(TypedDict):

    # ── Session ─────────────────────────────────────────────────────────────
    # Initialisé par build_initial_state() / main.py
    session_id:          Optional[str]
    conversation_id:     Optional[str]
    user_id:             Optional[str]
    travellerId:         Optional[str]           # → session_bootstrap
    user_type:           Optional[str]           # → session_bootstrap | load_profile_node  ("real" | "native")
    suggestion_mode:     Optional[str]           # → session_bootstrap | clarification_checker_node  ("exploratory" | "semi_exploratory" | "precise_plan")

    # ── Géolocalisation ──────────────────────────────────────────────────────
    # Fourni par le client mobile avant l'appel — jamais écrit par un node
    user_geolocation:    Optional[Dict[str, Any]]  # {lat: float, lng: float} | None

    # ── Message utilisateur ──────────────────────────────────────────────────
    # user_message     : main.py
    # normalized_message : → greeting_node
    # conversation_history : accumulé manuellement dans main.py
    user_message:         str
    normalized_message:   Optional[str]
    conversation_history: List[Dict[str, str]]

    # ── Intent / NLU ─────────────────────────────────────────────────────────
    # → intent_classifier_node
    # Structure : {primary_intent, secondary_intents, action_type, constraints, language, confidence}
    intent_result: Dict[str, Any]

    # ── Profil voyageur ──────────────────────────────────────────────────────
    # → load_profile_node (ProfileLoaderNode)
    # Structure :
    #   traveller_profile : {traveller_id, first_name, last_name, email, phone,
    #                        has_partner, child_count, baby_count, traveler_type}
    #   availability      : {outbound_date, return_date, duration_days, checkin_date}
    #   route             : {origin, destination}
    #   travel_preferences: {accommodation: {hotel_id, hotel_name, hotel_stars, hotel_zone,
    #                                        meal_plan, room_type, nights, booked_services,
    #                                        booked_service_names},
    #                        flights: {outbound: {}, return: {}},
    #                        transfer: {title, from, to, duration_minutes, type}}
    #   tourist_group     : {tourist_group_id, tourist_group_name, agency_name, tour_operator_name}
    #   tags              : {tags: [...], traveller_tags: [...]}   ← snake_case
    #   voucher_id        : str
    #   onboarding_preferences : {trip_type, travel_purpose: [...], culinary_interests: [...]}
    #                            ← TravellerPreferencesService, None si jamais capturées/skippées
    #                            (USER RÉEL et USER NATIF, keyé sur user_id — pas traveller_id)
    profile_data: Dict[str, Any]

    # ── Contexte fusionné ────────────────────────────────────────────────────
    # → context_merger_node  (fusion intent_result + profile_data)
    # Structure : {origin, destination, destination_source, hotel_name,
    #              start_date, end_date, duration_days, natural_date_text,
    #              travelers, budget_level, interests,
    #              activity_preferences, restaurant_preferences, flight_preferences,
    #              accommodation_preferences, is_family, travel_persona,
    #              primary_intent, secondary_intents, action_type}
    # travel_persona ("solo"|"couple"|"famille"|"groupe") : trait stable de
    # l'onboarding (onboarding_preferences.trip_type), jamais recalculé par tour
    merged_context: Dict[str, Any]

    # ── Disponibilité / validation commerciale ───────────────────────────────
    # → availability_checker_node
    # traveller_available : alias de trip_is_ongoing (bool)
    # availability_result : {trip_is_ongoing, outbound_date, return_date, days_remaining,
    #                        hotel_name, destination, destination_source,
    #                        booked_activity_ids, booked_time_slots}
    traveller_available: Optional[bool]
    availability_result: Optional[Dict[str, Any]]
    # → availability_checker_node — position temporelle dans le séjour
    # {day_index (1=arrivée), total_days, is_first_day, is_last_day,
    #  arrival_time (landing vol aller), departure_time (takeoff vol retour)}
    # Tout None/False si pas de voyage en cours (USER NATIF ou hors séjour)
    trip_position: Optional[Dict[str, Any]]
    # → availability_checker_node — ancres booking immuables (déjà payées)
    # {meal_plan, breakfast/lunch/dinner_included, hotel_name, hotel_zone,
    #  booked_services: [{name, date, status}], transfer}
    # None/vide pour USER NATIF
    booking_anchors: Optional[Dict[str, Any]]
    # → day_skeleton_node — structure de journée instantanée (Python pur)
    # {destination, duration_days, day_context, days: [{day_number, date, mode, slots}], display_text}
    # None si intent hors day_planning/trip_package
    day_skeleton: Optional[Dict[str, Any]]

    # ── Clarification ────────────────────────────────────────────────────────
    # → clarification_checker_node
    missing_required:       List[str]
    missing_optional:       List[str]
    blocking_fields:        List[str]
    decision_confidence:    Optional[str]        # "low" | "medium" | "high"
    clarification_needed:   bool
    clarification_question: Optional[str]
    clarification_focus:    List[str]
    clarification_type:     Optional[str]        # UNUSED — jamais écrit par clarification_checker_node

    # ── Routage ──────────────────────────────────────────────────────────────
    # → clarification_checker_node | BaseNode.fallback
    # Valeurs : "continue" | "ask_clarification" | "error"
    next_action: Optional[str]

    # ── Météo ────────────────────────────────────────────────────────────────
    # → weather_node
    weather_context: Optional[Dict[str, Any]]
    weather:         Dict[str, Any]              # DEPRECATED — jamais écrit, utiliser weather_context

    # ── Sémantique ───────────────────────────────────────────────────────────
    # → semantic_node
    global_keywords:    List[str]                # camelCase, alignés sur l'intent
    contextual_keywords: List[str]               # camelCase, contexte voyage spécifique
    semantic_query:     Optional[str]            # requête naturelle max 50 chars
    semantic_metadata:  Optional[Dict[str, Any]]
    semantic_cache_key: Optional[str]

    # ── Orchestration ────────────────────────────────────────────────────────
    # → orchestrator_node (LLM hybrid)
    # Ex : ["hotel_node", "activity_node", "restaurant_node"]
    requested_services:       List[str]
    # Contraintes par service — lues par chaque domain node
    # Ex : {"activity_node": {"max_duration_hours": 2.0, "exclude_activity_ids": [...]},
    #        "restaurant_node": {"meal_slot": "lunch", "optional_experience": false}}
    orchestrator_constraints: Optional[Dict[str, Any]]
    # Trace du raisonnement LLM de l'orchestrateur (debug / rapport)
    orchestrator_reasoning:   Optional[str]

    # ── Candidats par domaine ────────────────────────────────────────────────
    # → hotel_node | flight_node | restaurant_node | activity_node
    hotel_candidates:      List[Dict[str, Any]]
    flight_candidates:     List[Dict[str, Any]]
    restaurant_candidates: List[Dict[str, Any]]
    activity_candidates:   List[Dict[str, Any]]

    # ── Post-processing ──────────────────────────────────────────────────────
    # candidates     : → data_merger_node → constraint_validator_node  (fusion + filtrage)
    # ranked_results : → ranking_node  (score = 0.70 × user_score + 0.30 × business_score)
    # total_ranked   : → ranking_node
    # recommendations: RÉSERVÉ — recommendation_composer_node (Phase 5, non implémenté)
    # itinerary      : → day_planner_node  (None si intent hors day_planning/trip_package)
    candidates:      List[Dict[str, Any]]
    ranked_results:  List[Dict[str, Any]]
    total_ranked:    int
    recommendations: Dict[str, Any]             # RÉSERVÉ — non utilisé actuellement
    itinerary:       Dict[str, Any]

    # ── Pipeline informatif (travel_question / booking_question) ────────────
    # last_candidates   : chargé depuis Redis (session_manager) au début de chaque tour
    #                     contient les 3-4 candidats présentés au dernier tour de recommandation
    #                     format minimal : [{name, destination, address, phone, lat, lng, type}]
    #                     NE PAS confondre avec ranked_results (candidats du tour courant)
    # information_context : produit par information_node (Python rule-based)
    #                       lu par final_response_node pour formuler la réponse
    #                       format : {subtype, resolved_data, confidence, fallback_suggestion}
    last_candidates:    Optional[List[Dict[str, Any]]]
    information_context: Optional[Dict[str, Any]]

    # ── Réponse finale ───────────────────────────────────────────────────────
    # final_answer          : → final_response_node | recommendation_response_node
    # response_agent_result : → final_response_node  (objet structuré complet)
    # follow_up_needed      : → final_response_node  (bool — question de suivi détectée)
    # intent_handled        : → final_response_node  (intent traité dans cette réponse)
    # response_confidence   : → final_response_node  (0.0 – 1.0)
    final_answer:          Optional[str]
    response_agent_result: Optional[Dict[str, Any]]
    follow_up_needed:      Optional[bool]
    intent_handled:        Optional[str]
    response_confidence:   Optional[float]

    # ── Apprentissage (Phase 5) ──────────────────────────────────────────────
    feedback_event:  Dict[str, Any]   # produit par feedback_logger_node
    profile_written: Optional[bool]   # produit par profile_writer_node

    # ── Technique — accumulateurs LangGraph (operator.add) ───────────────────
    # Chaque node peut y appendre via BaseNode.__call__ (metrics) / BaseNode.fallback (errors)
    errors:       Annotated[List[Dict], operator.add]
    node_metrics: Annotated[List[Dict[str, Any]], operator.add]


def build_initial_state(
    user_message: str,
    conversation_id: Optional[str] = None,
    session_id: Optional[str] = None,
    user_id: Optional[str] = None,
    travellerId: Optional[str] = None,
) -> GraphState:
    """Crée un état initial propre pour une exécution du graphe."""

    return {
        # Session
        "user_message":      user_message,
        "conversation_id":   conversation_id,
        "session_id":        session_id,
        "user_id":           user_id,
        "travellerId":       travellerId,
        "user_type":         None,
        "suggestion_mode":   None,
        "user_geolocation":  None,

        # Message
        "normalized_message":   None,
        "conversation_history": [],

        # Intent NLU
        "intent_result": {},

        # Profil
        "profile_data": {},

        # Contexte fusionné
        "merged_context": {},

        # Disponibilité
        "traveller_available": None,
        "availability_result": None,
        "trip_position":       None,
        "booking_anchors":     None,
        "day_skeleton":        None,

        # Clarification
        "missing_required":       [],
        "missing_optional":       [],
        "blocking_fields":        [],
        "decision_confidence":    None,
        "clarification_needed":   False,
        "clarification_question": None,
        "clarification_focus":    [],
        "clarification_type":     None,

        # Routage
        "next_action": None,

        # Météo
        "weather_context": None,
        "weather":         {},           # DEPRECATED

        # Sémantique
        "global_keywords":     [],
        "contextual_keywords": [],
        "semantic_query":      None,
        "semantic_metadata":   {},
        "semantic_cache_key":  None,

        # Orchestration + candidats domaine
        "requested_services":       [],
        "orchestrator_constraints": None,
        "orchestrator_reasoning":   None,
        "hotel_candidates":      [],
        "flight_candidates":     [],
        "restaurant_candidates": [],
        "activity_candidates":   [],

        # Post-processing
        "candidates":       [],
        "ranked_results":   [],
        "total_ranked":     0,
        "recommendations":  {},
        "itinerary":        {},

        # Pipeline informatif
        "last_candidates":    None,
        "information_context": None,

        # Réponse
        "final_answer":          None,
        "response_agent_result": None,
        "follow_up_needed":      None,
        "intent_handled":        None,
        "response_confidence":   None,

        # Apprentissage (Phase 5)
        "feedback_event":  {},
        "profile_written": None,

        # Technique
        "node_metrics": [],
        "errors":       [],
    }
