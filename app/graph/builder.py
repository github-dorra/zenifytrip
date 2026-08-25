from typing import List, Union

from langgraph.graph import StateGraph, END, START

from app.graph.state import GraphState
from app.nodes.conversation.greeting_node import GreetingNode
from app.nodes.comprehension.intent_classifier_node import IntentClassifierNode
from app.nodes.comprehension.clarification_checker_node import ClarificationCheckerNode
from app.nodes.user_profile.load_profile_node import ProfileLoaderNode
from app.nodes.merge.context_merger_node import ContextMergerNode
from app.nodes.conversation.final_response_node import FinalResponseNode
from app.nodes.core.session_bootstrap import bootstrap_session
from app.nodes.Logistics.weather_node import WeatherNode
from app.nodes.recommendation.context.semantic_node import SemanticAgentNode
from app.nodes.recommendation.orchestration.orchestrator_node import OrchestratorNode
from app.nodes.recommendation.domain.hotel_node import HotelNode
from app.nodes.recommendation.domain.flight_node import FlightNode
from app.nodes.recommendation.domain.restaurant_node import RestaurantNode
from app.nodes.recommendation.domain.activity_node import ActivityNode
from app.nodes.recommendation.context.availability_checker_node import AvailabilityCheckerNode
from app.nodes.recommendation.postprocessing.data_merger_node import DataMergerNode
from app.nodes.recommendation.postprocessing.constraint_validator_node import ConstraintValidatorNode
from app.nodes.recommendation.postprocessing.ranking_node import RankingNode
from app.nodes.recommendation.postprocessing.recommendation_response_node import RecommendationResponseNode
from app.nodes.recommendation.postprocessing.day_planner_node import DayPlannerNode
from app.nodes.recommendation.postprocessing.day_skeleton_node import DaySkeletonNode
from app.nodes.conversation.information_node import InformationNode, _WEATHER_KW
from app.nodes.conversation.informative_response_node import InformativeResponseNode
from app.nodes.shared.feedback_logger_node import FeedbackLoggerNode
from app.nodes.user_profile.profile_writer_node import ProfileWriterNode


# Intents qui nécessitent le pipeline complet (weather → semantic → orchestrator → domaines)
RECOMMENDATION_INTENTS = {
    "flight_recommendation",
    "accommodation_recommendation",
    "restaurant_recommendation",
    "activity_recommendation",
    "day_planning",
    "trip_package_recommendation",
}

# Intents routés vers le pipeline informatif (information_node → final_response)
INFORMATIVE_INTENTS = {"travel_question", "booking_question"}

# Intents qui méritent un squelette de journée immédiat avant le pipeline complet
SKELETON_INTENTS = {"day_planning", "trip_package_recommendation", "activity_recommendation"}

# Intents dont le feedback doit passer par Phase 5 avant réponse
LEARNING_INTENTS = {"feedback", "profile_update"}


# Mots-clés indiquant que le message parle d'une RÉSERVATION PERSONNELLE du voyageur.
# Si l'intent_classifier classe ces messages en travel_question (mauvaise clasif LLM),
# on force quand même availability_checker pour charger trip_is_ongoing / booking_anchors.
_BOOKING_FORCE_KW = frozenset({
    "mon vol", "mon hôtel", "mon hotel", "ma chambre",
    "ma réservation", "check-in", "mon billet", "ma résa",
    "heure de vol", "heure du vol", "décollage", "atterrissage",
    "numéro de vol", "vol retour", "vol aller",
})


def route_after_context_merge(state: GraphState) -> str:
    """
    Saute availability_checker pour travel_question PURE (pas de données booking nécessaires).
    Garde availability_checker pour booking_question et pour les travel_question contenant
    des mots-clés de réservation personnelle (guard contre mauvaise classification LLM).
    """
    primary_intent = (state.get("intent_result") or {}).get("primary_intent", "unsupported")
    if primary_intent == "travel_question":
        msg = (state.get("normalized_message") or state.get("user_message") or "").lower()
        if any(kw in msg for kw in _BOOKING_FORCE_KW):
            return "availability_checker"   # "mon vol…" → besoin des données API booking
        return "clarification_checker"      # factuel pur → on saute availability_checker
    return "availability_checker"


def route_after_clarification_checker(state: GraphState) -> str:
    intent_result  = state.get("intent_result") or {}
    primary_intent = intent_result.get("primary_intent", "unsupported")
    next_action    = state.get("next_action")

    if primary_intent in ("greeting", "unsupported"):
        return "final_response"

    if next_action == "ask_clarification":
        return "final_response"

    # travel_question : weather_node uniquement si la question porte sur météo/saison/baignade
    if primary_intent == "travel_question":
        msg = (state.get("normalized_message") or state.get("user_message") or "").lower()
        if any(kw in msg for kw in _WEATHER_KW):
            return "weather_only"
        return "information_node"
    # booking_question : pas besoin de météo
    if primary_intent == "booking_question":
        return "information_node"

    # feedback / profile_update → Phase 5 d'abord (apprentissage), puis réponse
    if primary_intent in LEARNING_INTENTS:
        return "feedback_path"

    # Autres intents non-recommandation → réponse directe
    if primary_intent not in RECOMMENDATION_INTENTS:
        return "final_response"

    # Pipeline recommandation complet
    # day_skeleton uniquement pour les intents de planification/activités
    if primary_intent in SKELETON_INTENTS:
        return "day_skeleton"
    return "weather_direct"


def route_after_weather_node(state: GraphState) -> str:
    """Après weather_node : pipeline informatif (travel_question) ou pipeline complet (recommendation)."""
    intent_result  = state.get("intent_result") or {}
    primary_intent = intent_result.get("primary_intent", "unsupported")
    if primary_intent in INFORMATIVE_INTENTS:
        return "information_node"
    return "semantic_node"


def route_after_profile_writer(state: GraphState) -> str:
    """
    Après profile_writer :
    - chemin recommandation (final_answer posé par recommendation_response) → END
    - chemin feedback/profile_update (aucune réponse encore) → final_response
    """
    if state.get("final_answer"):
        return "__end__"
    return "final_response"


def route_after_orchestrator(state: GraphState) -> Union[str, List[str]]:
    """
    Fan-out vers les services domaine sélectionnés par OrchestratorNode.

    - [] → final_response (intents conversationnels : travel_question, greeting...)
    - ["hotel_node"] → hotel_node seul
    - ["hotel_node", "restaurant_node"] → fan-out parallèle LangGraph
    """
    services = state.get("requested_services") or []
    if not services:
        return "final_response"
    return services


def build_graph():
    graph = StateGraph(GraphState)

    # ── PHASE 1 : COMPRÉHENSION ───────────────────────────────────────────────
    # fan-out : greeting + session_bootstrap en parallèle, puis intent + profile en parallèle
    graph.add_node("greeting",              GreetingNode())              # [tech] normalise message (strip/lower)
    graph.add_node("session_bootstrap",     bootstrap_session)           # [tech] API interne → travellerId, user_type, suggestion_mode
    graph.add_node("intent_classifier",     IntentClassifierNode())      # [LLM]  Gemini 2.0 Flash — classifie intent + extrait contraintes JSON
    graph.add_node("profile_loader",        ProfileLoaderNode())         # [tech] MongoDB cache (TTL 30j) ou API agence → profil complet
    graph.add_node("context_merge",         ContextMergerNode())         # [tech] fusionne intent_result + profile_data → merged_context
    graph.add_node("availability_checker",  AvailabilityCheckerNode())   # [tech] API interne → trip_position, booking_anchors, destination L1/L2/L3
    graph.add_node("clarification_checker", ClarificationCheckerNode())  # [tech] rule-based → champs manquants, suggestion_mode, next_action

    # ── PHASE 2 : ENRICHISSEMENT CONTEXTE ────────────────────────────────────
    graph.add_node("day_skeleton", DaySkeletonNode())    # [tech] squelette Python pur <10ms — streamé immédiatement (SKELETON_INTENTS uniquement)
    graph.add_node("weather_node", WeatherNode())        # [tech] API OpenWeather → weather_context (météo/saison/baignade ou pipeline complet)
    graph.add_node("semantic_node", SemanticAgentNode()) # [LLM]  Gemini 2.0 Flash — extrait semantic_keywords + tags depuis merged_context

    # ── PHASE 3 : ORCHESTRATION ───────────────────────────────────────────────
    graph.add_node("orchestrator", OrchestratorNode())   # [LLM]  Gemini 3.1 Flash Lite — hybrid (règles 80% + LLM si voyage actif/repas inclus/dernier jour)

    # ── PHASE 4 : DOMAINES — fan-out conditionnel ────────────────────────────
    graph.add_node("hotel_node",      HotelNode())        # [tech] API interne Tier1 (hotel-services) + Tier2 (catalogue 746 hôtels), haversine
    graph.add_node("flight_node",     FlightNode())       # [tech] API interne 272 vols + enrichissement destination (tunisia_destinations)
    graph.add_node("restaurant_node", RestaurantNode())   # [tech] MongoDB Atlas Search Tier1 (26 575 docs) + SerpApi Tier2 fallback
    graph.add_node("activity_node",   ActivityNode())     # [tech] API interne + MongoDB Atlas (ThreadPoolExecutor, rapidfuzz dedup ≥75)

    # ── PHASE 4 : POST-PROCESSING ─────────────────────────────────────────────
    graph.add_node("data_merger",          DataMergerNode())          # [tech] fusionne les 4 listes → candidates (priorité par intent)
    graph.add_node("constraint_validator", ConstraintValidatorNode()) # [tech] filtre dur — seul point d'exclusion : is_available=False
    graph.add_node("ranking_node",         RankingNode())             # [tech] scoring V2 multiplicatif : user_score × business_boost × avail_factor
    graph.add_node("day_planner",          DayPlannerNode())          # [LLM]  Gemini 2.0 Flash — itinéraire contextualisé (anchors, trip_position, météo)

    # ── PIPELINE INFORMATIF (travel_question / booking_question) ─────────────
    graph.add_node("information_node",      InformationNode())         # [tech] rule-based → subtype détecté, resolved_data assemblé (0 LLM)
    graph.add_node("informative_response",  InformativeResponseNode()) # [LLM]  Agent 3 : réponse experte (visa/prix/booking/factuel stable)

    # ── RÉPONSE — 2 agents LLM distincts selon le chemin ─────────────────────
    graph.add_node("final_response",          FinalResponseNode())          # [LLM]  Gemini 2.0 Flash — Agent 1 : clarification / info / greeting
    graph.add_node("recommendation_response", RecommendationResponseNode()) # [LLM]  Gemini 2.0 Flash — Agent 2 : présentation ranked_results

    # ── PHASE 5 : APPRENTISSAGE ───────────────────────────────────────────────
    graph.add_node("feedback_logger", FeedbackLoggerNode()) # [tech] mine liked/rejected depuis conversation_history (session_memory.py)
    graph.add_node("profile_writer",  ProfileWriterNode())  # [tech] persiste préférences cross-session dans Redis (TTL 30j)
    
    
    

    # ── EDGES PHASE 1 ────────────────────────────────────────────────────────
    graph.add_node("init", lambda state: state)
    graph.add_edge(START, "init")
    graph.add_edge("init", "greeting")
    graph.add_edge("init", "session_bootstrap")

    graph.add_edge("greeting",          "intent_classifier")
    graph.add_edge("session_bootstrap", "profile_loader")

    # Fan-in : intent + profil → context_merge (même profondeur → pas de double exécution)
    graph.add_edge("intent_classifier", "context_merge")
    graph.add_edge("profile_loader",    "context_merge")

    # travel_question → saute availability_checker (économise ~2.4s d'appel API inutile)
    # tout le reste → availability_checker → clarification_checker
    graph.add_conditional_edges(
        "context_merge",
        route_after_context_merge,
        {
            "clarification_checker": "clarification_checker",
            "availability_checker":  "availability_checker",
        },
    )
    graph.add_edge("availability_checker", "clarification_checker")

    # Routage : clarification → final_response | information_node | pipeline recommandation
    graph.add_conditional_edges(
        "clarification_checker",
        route_after_clarification_checker,
        {
            "day_skeleton":     "day_skeleton",     # planning/activités : skeleton immédiat
            "weather_direct":   "weather_node",     # autres recommandations : weather direct
            "weather_only":     "weather_node",     # travel_question météo : weather direct
            "information_node": "information_node",
            "final_response":   "final_response",
            "feedback_path":    "feedback_logger",  # feedback/profile_update → Phase 5
        },
    )
    graph.add_edge("day_skeleton",         "weather_node")
    graph.add_edge("information_node",     "informative_response")
    graph.add_edge("informative_response", END)

    # ── EDGES PHASE 2 ────────────────────────────────────────────────────────
    graph.add_conditional_edges(
        "weather_node",
        route_after_weather_node,
        {
            "information_node": "information_node",
            "semantic_node":    "semantic_node",
        },
    )
    graph.add_edge("semantic_node", "orchestrator")

    # ── EDGES PHASE 3 — fan-out conditionnel ─────────────────────────────────
    graph.add_conditional_edges(
        "orchestrator",
        route_after_orchestrator,
        {
            "hotel_node":      "hotel_node",
            "flight_node":     "flight_node",
            "restaurant_node": "restaurant_node",
            "activity_node":   "activity_node",
            # intents conversationnels (travel_question, etc.) → Agent 1
            "final_response":  "final_response",
        },
    )

    # ── EDGES PHASE 4 — fan-in vers data_merger ───────────────────────────────
    graph.add_edge("hotel_node",      "data_merger")
    graph.add_edge("flight_node",     "data_merger")
    graph.add_edge("restaurant_node", "data_merger")
    graph.add_edge("activity_node",   "data_merger")

    # data_merger → constraint_validator → ranking_node → day_planner → recommendation_response
    graph.add_edge("data_merger",             "constraint_validator")
    graph.add_edge("constraint_validator",    "ranking_node")
    graph.add_edge("ranking_node",            "day_planner")
    graph.add_edge("day_planner",             "recommendation_response")

    # ── PHASE 5 — après recommendation_response ───────────────────────────────
    # recommendation_response → feedback_logger → profile_writer → END
    # feedback/profile_update  → feedback_logger → profile_writer → final_response → END
    graph.add_edge("recommendation_response", "feedback_logger")
    graph.add_edge("feedback_logger",         "profile_writer")
    graph.add_conditional_edges(
        "profile_writer",
        route_after_profile_writer,
        {
            "final_response": "final_response",  # chemin feedback : réponse à l'utilisateur
            "__end__":        END,               # chemin recommandation : déjà répondu
        },
    )

    # final_response (Agent 1) → END directement (pas de recommandation = pas de feedback)
    graph.add_edge("final_response", END)

    return graph.compile()
