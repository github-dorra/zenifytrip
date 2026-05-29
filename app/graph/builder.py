from langgraph.graph import StateGraph, END, START

from app.graph.state import GraphState
from app.nodes.conversation.greeting_node import GreetingNode
from app.nodes.comprehension.intent_classifier_node import IntentClassifierNode
from app.nodes.comprehension.clarification_checker_node import ClarificationCheckerNode
from app.nodes.user_profile.profile_loader_node import ProfileLoaderNode
from app.nodes.merge.context_merger_node import ContextMergerNode
from app.nodes.conversation.final_response_node import FinalResponseNode
from app.nodes.core.session_bootstrap import bootstrap_session
from app.nodes.Logistics.weather_node import WeatherNode
from app.nodes.recommendation.context.semantic_node import SemanticAgentNode


TRAVEL_INTENTS = {
    "travel_question",
    "booking_question",
    "profile_update",
    "flight_recommendation",
    "accommodation_recommendation",
    "restaurant_recommendation",
    "activity_recommendation",
    "day_planning",
    "trip_package_recommendation",
}


def route_after_clarification_checker(state: GraphState) -> str:
    intent_result   = state.get("intent_result") or {}
    primary_intent  = intent_result.get("primary_intent", "unsupported")
    next_action     = state.get("next_action")

    if primary_intent in ("greeting", "unsupported"):
        return "final_response"

    if next_action == "ask_clarification":
        return "final_response"

    if primary_intent in TRAVEL_INTENTS:
        return "weather_node"

    return "final_response"


def build_graph():
    graph = StateGraph(GraphState)

    # --- nodes ---
    graph.add_node("greeting",              GreetingNode())
    graph.add_node("session_bootstrap",     bootstrap_session)
    graph.add_node("intent_classifier",     IntentClassifierNode())
    graph.add_node("profile_loader",        ProfileLoaderNode())
    graph.add_node("context_merge",         ContextMergerNode())
    graph.add_node("clarification_checker", ClarificationCheckerNode())
    graph.add_node("weather_node",          WeatherNode())
    graph.add_node("semantic_node",         SemanticAgentNode())
    graph.add_node("final_response",        FinalResponseNode())


    graph.add_edge(START, "greeting")
    graph.add_edge(START, "session_bootstrap")

    graph.add_edge("greeting",          "intent_classifier")
    graph.add_edge("session_bootstrap", "profile_loader")

    graph.add_edge("intent_classifier", "context_merge")
    graph.add_edge("profile_loader",    "context_merge")

    graph.add_edge("context_merge", "clarification_checker")

    # --- Routage conditionnel après clarification ---
    graph.add_conditional_edges(
        "clarification_checker",
        route_after_clarification_checker,
        {
            "weather_node":   "weather_node",
            "final_response": "final_response",
        },
    )

    # --- Phase 2 : enrichissement contexte ---
    graph.add_edge("weather_node",  "semantic_node")
    graph.add_edge("semantic_node", "final_response")

    graph.add_edge("final_response", END)

    return graph.compile()
