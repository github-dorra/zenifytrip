# Project Anatomy — ZenifyTrip

## Entry Point
- `app/main.py` — boucle CLI, streaming LangGraph, SessionManager, conversation_history

## Graph
- `app/graph/builder.py` — topologie complète, routing functions, RECOMMENDATION_INTENTS, INFORMATIVE_INTENTS
- `app/graph/state.py` — GraphState TypedDict + build_initial_state()

## Nodes
### Core
- `app/nodes/core/Base_node.py` — BaseNode ABC + NodeConfig dataclass
- `app/nodes/core/session_bootstrap.py` — résout traveller_id via API

### Conversation
- `app/nodes/conversation/greeting_node.py`
- `app/nodes/conversation/final_response_node.py` — Agent 1 (clarification + pipeline informatif)
- `app/nodes/conversation/information_node.py` — pipeline informatif rule-based (5 subtypes)

### Comprehension
- `app/nodes/comprehension/intent_classifier_node.py`
- `app/nodes/comprehension/clarification_checker_node.py`

### User Profile
- `app/nodes/user_profile/load_profile_node.py`

### Merge
- `app/nodes/merge/context_merger_node.py`

### Recommendation / Context
- `app/nodes/recommendation/context/availability_checker_node.py` — +trip_position +booking_anchors
- `app/nodes/recommendation/context/semantic_node.py`

### Recommendation / Orchestration
- `app/nodes/recommendation/orchestration/orchestrator_node.py`

### Recommendation / Domain
- `app/nodes/recommendation/domain/hotel_node.py`
- `app/nodes/recommendation/domain/flight_node.py`
- `app/nodes/recommendation/domain/restaurant_node.py`
- `app/nodes/recommendation/domain/activity_node.py`

### Recommendation / Postprocessing
- `app/nodes/recommendation/postprocessing/data_merger_node.py`
- `app/nodes/recommendation/postprocessing/constraint_validator_node.py`
- `app/nodes/recommendation/postprocessing/ranking_node.py` — scoring V2 multiplicatif
- `app/nodes/recommendation/postprocessing/day_skeleton_node.py` — squelette <10ms
- `app/nodes/recommendation/postprocessing/day_planner_node.py`
- `app/nodes/recommendation/postprocessing/recommendation_response_node.py` — Agent 2

### Logistics
- `app/nodes/Logistics/weather_node.py`

## Services
- `app/services/session_manager.py` — Redis session (last_candidates, weather_context, etc.)
- `app/services/cache_service.py` — cache in-memory + JSON file (API data)
- `app/services/profile_service.py`
- `app/services/hotel_service.py`, `flight_service.py`
- `app/services/mongo_restaurant_service.py`, `restaurant_service.py`
- `app/services/activity_service/` — InternalActivityService + MongoActivityService

## Config
- `app/config/settings.py` — TOUTES les constantes globales (TTL, weights, session params)
- `app/config/definitions.py` — NodeConfig instances (LLM configs)
- `app/config/redis_config.py` — pool Redis (r = None si down)
- `app/config/mongodb.py` — connexion Atlas

## Prompts
- `app/prompts/final_response_prompt.py` — Agent 1 (clarification + informatif)
- `app/prompts/recommendation/recommendation_response_prompt.py` — Agent 2
- `app/prompts/comprehension/intent_classifier_prompt.py`
- `app/prompts/recommendation/semantic_prompt.py`
- `app/prompts/recommendation/orchestrator_prompt.py`

## Schemas
- `app/schemas/intent_schema.py`, `reponse_schema.py`, `profile_schema.py`
- `app/schemas/recommendation_schema.py`, `ranking_schema.py`, `activity_schema.py`

## Data
- `app/data/tunisia_destinations.py` — AIRPORT_COORDS, city_to_airports()
- `app/.cache/zenifytrip_cache.json` — cache persisté (hotels, flights, etc.)
