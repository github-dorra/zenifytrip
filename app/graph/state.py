import operator
from typing import TypedDict, Annotated, List, Dict, Any, Optional


class GraphState(TypedDict):

    # ── Session ───────────────────────────────────────────────────
    session_id:          Optional[str]
    conversation_id:     Optional[str]
    user_id:             Optional[str]
    travellerId:         Optional[str]
    user_type:           Optional[str]   # "real" | "native"

    # ── Message utilisateur ───────────────────────────────────────
    user_message:        str
    normalized_message:  Optional[str]
    conversation_history: List[Dict[str, str]]

    # ── Intent / NLU (intent_classifier_node) ────────────────────
    intent_result: Dict[str, Any]
    # contient : primary_intent, secondary_intents, action_type,
    #            constraints, language, confidence

    # ── Profil voyageur (profile_loader_node) ────────────────────
    profile_data: Dict[str, Any]

    # ── Contexte fusionné (context_merger_node) ───────────────────
    merged_context: Dict[str, Any]

    # ── Clarification (clarification_checker_node) ────────────────
    missing_required:       List[str]
    missing_optional:       List[str]
    blocking_fields:        List[str]
    suggestion_mode:        Optional[str]
    decision_confidence:    Optional[str]
    clarification_needed:   bool
    clarification_question: Optional[str]
    clarification_focus:    List[str]
    clarification_type:     Optional[str]

    # ── Routage ───────────────────────────────────────────────────
    next_action: Optional[str]

    # ── Disponibilité / validation commerciale ────────────────────
    traveller_available: Optional[bool]
    availability_result: Optional[Dict[str, Any]]

    # ── Météo ─────────────────────────────────────────────────────
    weather_context: Optional[Dict[str, Any]]
    weather:         Dict[str, Any]

    # ── Sémantique (semantic_node) ────────────────────────────────
    global_keywords:    List[str]
    contextual_keywords: List[str]
    semantic_query:     Optional[str]
    semantic_metadata:  Optional[Dict[str, Any]]
    semantic_cache_key: Optional[str]

    # ── Recommandation — candidats domaine ────────────────────────
    requested_services:    List[str]
    hotel_candidates:      List[Dict[str, Any]]
    flight_candidates:     List[Dict[str, Any]]
    restaurant_candidates: List[Dict[str, Any]]
    activity_candidates:   List[Dict[str, Any]]

    # ── Recommandation — post-processing ─────────────────────────
    candidates:    List[Dict[str, Any]]   # fusion tous domaines
    ranked_results: List[Dict[str, Any]]  # après ranking_node
    recommendations: Dict[str, Any]       # après recommendation_composer
    itinerary:     Dict[str, Any]         # après day_planner_node

    # ── Réponse ───────────────────────────────────────────────────
    final_answer: Optional[str]

    # ── Apprentissage ─────────────────────────────────────────────
    feedback_event: Dict[str, Any]

    # ── Technique — accumulateurs LangGraph ───────────────────────
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

        # Message
        "normalized_message":   None,
        "conversation_history": [],

        # Intent NLU
        "intent_result": {},

        # Profil
        "profile_data": {},

        # Contexte fusionné
        "merged_context": {},

        # Clarification
        "missing_required":       [],
        "missing_optional":       [],
        "blocking_fields":        [],
        "suggestion_mode":        None,
        "decision_confidence":    None,
        "clarification_needed":   False,
        "clarification_question": None,
        "clarification_focus":    [],
        "clarification_type":     None,

        # Routage
        "next_action": None,

        # Disponibilité
        "traveller_available": None,
        "availability_result": None,

        # Météo
        "weather_context": None,
        "weather":         {},

        # Sémantique
        "global_keywords":     [],
        "contextual_keywords": [],
        "semantic_query":      None,
        "semantic_metadata":   {},
        "semantic_cache_key":  None,

        # Candidats domaine
        "requested_services":    [],
        "hotel_candidates":      [],
        "flight_candidates":     [],
        "restaurant_candidates": [],
        "activity_candidates":   [],

        # Post-processing
        "candidates":       [],
        "ranked_results":   [],
        "recommendations":  {},
        "itinerary":        {},

        # Réponse
        "final_answer": None,

        # Apprentissage
        "feedback_event": {},

        # Technique
        "node_metrics": [],
        "errors":       [],
    }
