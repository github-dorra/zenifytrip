import asyncio
from langgraph.graph import StateGraph,END 
from app.graph.state import GraphState
from app.nodes.conversation.greeting_node import GreetingNode
from app.nodes.comprehension.intent_classifier_node import IntentClassifierNode
from app.nodes.comprehension.clarification_checker_node import ClarificationCheckerNode
from app.nodes.user_profile.profile_loader_node import ProfileLoaderNode
from app.nodes.merge.context_merger_node import ContextMergerNode
from app.nodes.conversation.final_response_node import FinalResponseNode


    
    # condition function
def route_after_intent_classifier(state):
        """
        Decide the next node to execute after IntentClassifierNode.
        """
        primary_intent = state.get("primary_intent") 

        # greeting / unsupported 
        if primary_intent in  ["greeting","unsupported"]:
            return "response_agent"

    
        # other intent 
        travel_intents = [
        "travel_question",
        "booking_question",
        "profile_update",
        "flight_recommendation",
        "accommodation_recommendation",
        "restaurant_recommendation",
        "activity_recommendation",
        "day_planning",
        "trip_package_recommendation",
    ]
        if primary_intent in travel_intents:
            return "clarification_checker"
        
        #fallback
        return "response_final"
        
    
def route_after_clarification_checker(state: GraphState) -> str: 
    if state.get("next_action") == "ask_clarification": 
        return "final_response" 
    recommendation_mode = state.get("recommendation_mode") 
    primary_intent = state.get("primary_intent") 
    # Plus tard, tu remplaceras ces routes par les vrais agents. 
    if recommendation_mode == "exploratory": 
        return "final_response" 
    # plus tard: trip_inspiration_agent 
    if recommendation_mode == "precise_plan": 
        return "final_response" 
    # plus tard: day_planner_agent 
    if recommendation_mode == "booking": 
        return "final_response" 
    # plus tard: booking / availability / hotel / flight agent 
    return "final_response" 



def build_graph():
    # Initialize the graph
    graph = StateGraph(GraphState)


    # Add nodes
    graph.add_node("greeting", GreetingNode())
    graph.add_node("intent_classifier", IntentClassifierNode())
    graph.add_node("profile_loader",ProfileLoaderNode()),
    graph.add_node("context_merge", ContextMergerNode()),
    graph.add_node("clarification_checker", ClarificationCheckerNode())
    graph.add_node("final_response", FinalResponseNode())
    
    
    
    #define the entry node 
    graph.set_entry_point("greeting")
    
    #   add edges
    graph.add_edge("greeting", "intent_classifier")
    graph.add_edge("greeting", "profile_loader")
    graph.add_edge("intent_classifier", "context_merge")
    graph.add_edge("profile_loader", "context_merge")
    graph.add_edge("context_merge", "clarification_checker")
    graph.add_edge("clarification_checker", "final_response")
    graph.add_edge("final_response", END)

    #graph.add_conditional_edges(
     # "clarification_checker",
      #  route_after_intent_classifier,
       # { "final_response": "final_response",
        # "context_merge": "clarification_checker",
       # )

    #graph.add_edge("constraint_extractor", "clarification_checker")
    #graph.add_conditional_edges( 
           # "clarification_checker", 
           # route_after_clarification_checker, 
            #{ 
          #  "final_response": "final_response", }, ) 
    #graph.add_edge("final_response", END)
    
    
    

    return graph.compile()