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

    # profile_update, feedback → réponse directe (pas de pipeline)
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
    graph.add_node("greeting",              GreetingNode())
    graph.add_node("session_bootstrap",     bootstrap_session)
    graph.add_node("intent_classifier",     IntentClassifierNode())
    graph.add_node("profile_loader",        ProfileLoaderNode())
    graph.add_node("availability_checker",  AvailabilityCheckerNode())
    graph.add_node("context_merge",         ContextMergerNode())
    graph.add_node("clarification_checker", ClarificationCheckerNode())

    # ── PHASE 2 : ENRICHISSEMENT CONTEXTE ────────────────────────────────────
    graph.add_node("weather_node",  WeatherNode())
    graph.add_node("semantic_node", SemanticAgentNode())

    # ── PHASE 3 : ORCHESTRATION ───────────────────────────────────────────────
    graph.add_node("orchestrator", OrchestratorNode())

    # ── PHASE 4 : RECOMMANDATION (domaines) ──────────────────────────────────
    graph.add_node("hotel_node",      HotelNode())
    graph.add_node("flight_node",     FlightNode())
    graph.add_node("restaurant_node", RestaurantNode())
    graph.add_node("activity_node",   ActivityNode())

    # ── PHASE 4 : POST-PROCESSING ─────────────────────────────────────────────
    graph.add_node("data_merger",          DataMergerNode())
    graph.add_node("constraint_validator", ConstraintValidatorNode())
    graph.add_node("ranking_node",         RankingNode())
    graph.add_node("day_planner", DayPlannerNode())
    graph.add_node("day_skeleton", DaySkeletonNode())

    # ── PIPELINE INFORMATIF ───────────────────────────────────────────────────
    # travel_question / booking_question → context enrichi → final_response (Agent 1)
    graph.add_node("information_node",            InformationNode())

    # ── RÉPONSE — 2 agents distincts ──────────────────────────────────────────
    # Agent 1 : clarification / conversations / pipeline informatif
    graph.add_node("final_response",             FinalResponseNode())
    # Agent 2 : présentation des recommandations réelles (chemin data_merger)
    graph.add_node("recommendation_response",    RecommendationResponseNode())

    # ── PHASE 5 : APPRENTISSAGE ───────────────────────────────────────────────
    graph.add_node("feedback_logger",  FeedbackLoggerNode())
    graph.add_node("profile_writer",   ProfileWriterNode())
    
    
    

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

    # availability_checker APRÈS context_merge, AVANT clarification_checker
    graph.add_edge("context_merge",        "availability_checker")
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
        },
    )
    graph.add_edge("day_skeleton",       "weather_node")
    graph.add_edge("information_node",   "final_response")

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
    graph.add_edge("recommendation_response", "feedback_logger")
    graph.add_edge("feedback_logger",         "profile_writer")
    graph.add_edge("profile_writer",          END)

    # final_response (Agent 1) → END directement (pas de recommandation = pas de feedback)
    graph.add_edge("final_response", END)

    return graph.compile()
