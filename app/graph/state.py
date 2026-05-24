import operator
from typing import TypedDict, Annotated, List, Dict, Any, Optional

class GraphState(TypedDict):
    
    # Session
    session_id: str
    user_id: str
    travellerId: Optional[str]
    user_type: Optional[str]   # "real" | "native"
    
    # User message
    user_message: str
    normalized_message: str
    conversation_history: List[Dict[str, str]]
    
    # Intent NLU agent output
    intent_result: Dict[str, Any]

    # profil_loader_data output 
    profile_data: dict[str, Any]
    
    # merge context output 
    merged_context: dict[str, Any]
    
    # clarification checker output 
    missing_required: List[str]
    missing_optional: List[str]
    blocking_fields: List[str]
    suggestion_mode: Optional[str]
    decision_confidence: Optional[str]
    clarification_needed: bool
    clarification_question: Optional[str]
    clarification_focus: List[str]
    clarification_type: Optional[str]
    

    #routing 
    next_action: Optional[str]
    
    
    #  Availability / commercial validation
    traveller_available: Optional[bool]
    availability_result: Optional[Dict[str, Any]]
    
    
    # weather context output 
    weather_context: Optional[Dict[str, Any]]


    # Context - added later
    user_profile: Dict[str, Any]
    global_keywords: List[str]
    contextual_keywords: List[str]
    semantic_query: Optional[str]
    semantic_metadata: Optional[Dict[str, Any]]
    semantic_cache_key: Optional[str]
    weather: Dict[str, Any]
    
    # Recommendation - added later
    requested_services: List[str]
    hotel_candidates: List[Dict[str, Any]]
    restaurant_candidates: List[Dict[str, Any]]
    activity_candidates: List[Dict[str, Any]]
    flight_candidates: List[Dict[str, Any]]
    candidates: List[Dict[str, Any]]
    ranked_results: List[Dict[str, Any]]
    recommendations: Dict[str, Any]
    itinerary: Dict[str, Any]

    # Response
    final_answer: Optional[str]

    # Logging
    feedback_event: Dict[str, Any]

    # Errors
    errors: Annotated[List[Dict], operator.add]
    node_metrics: Annotated[List[Dict[str, Any]], operator.add]  
    # operator.add is used to concatenate lists of metrics from # nodes 
    # in a single list on a state without ecrasing previous metrics when we do state updates in nodes.

def build_initial_state(
    user_message: str,
    conversation_id: Optional[str] = None,
    session_id: Optional[str] = None,
    user_id: Optional[str] = None,
    travellerId: Optional[str] = None,
) -> GraphState:
    """
    Creates a clean initial state for one graph execution.
    """

    return {
        "user_message": user_message,
        "conversation_id": conversation_id,
        "session_id": session_id,
        "user_id": user_id,
        "travellerId": travellerId,
        "user_type": None,

        # input
        "normalized_message": None,
        "conversation_history": [],

        # intent output 
        "primary_intent": None,
        "secondary_intents": [],
        "action_type": None,
        "constraints": {},   # include all 
        "language": None,

        # profile
        "profile_data": {},  

        # merge profile_data with intent fields 
        "merged_context": {},

        # routing
        "next_action": None,
        
        #clarification checker output 
        "missing_required": [],
        "missing_optional": [],
        "blocking_fields": [],
        "suggestion_mode": None,
        "decision_confidence": None,
        "clarification_needed": False,
        "clarification_question":None ,
        "clarification_focus": [],

        "route_reason": None,

        "traveller_available": None,
        "availability_result": None,
        
        "weather_context":None,

        
        # semantic
        "global_keywords": [],
        "contextual_keywords": [],
        "semantic_query": None,
        "semantic_metadata": {},
        "semantic_cache_key": None,
        "weather": {},

        "execution_plan": None,
        "validated_execution_plan": None,

        "flight_options": [],
        "accommodation_options": [],
        "restaurant_options": [],
        "activity_options": [],
        "logistics_result": None,

        "merged_data": None,
        "normalized_data": None,

        "ranked_recommendations": None,
        "selected_flight": None,
        "selected_accommodation": None,
        "selected_restaurants": [],
        "selected_activities": [],

        "day_plan": None,
        
        
        # output 
        "final_answer": None,

        "profile_updates": None,
        "feedback_log": None,

        "node_metrics": [],
        "errors": [],
    }