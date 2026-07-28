# Wolf Memory

## 2026-07-28 — Sprint 2 : Pipeline Informatif

### Ce qui a été construit
Pipeline pour travel_question / booking_question :
`clarification_checker → information_node → final_response`

### information_node (rule-based, 0 LLM)
- 5 subtypes : follow_up_place, weather, booking_info, session_planning, factual
- Détection par mots-clés (frozensets) sur msg_lower
- Résolution par `last_candidates`, `weather_context`, `availability_result`, `booking_anchors`
- Retourne `information_context = {subtype, resolved_data, confidence, fallback_suggestion}`
- Confidence < 0.55 pour follow_up_place → fallback_suggestion = "Google Maps"

### Décision architecturale
- travel_question ne passe PLUS par weather/semantic/orchestrator/domain nodes
- Route directe : information_node → final_response (Agent 1 existant)
- Pas de nouveau LLM — le final_response_node consomme information_context

### Routing builder.py
- INFORMATIVE_INTENTS = {"travel_question", "booking_question"}
- route_after_clarification_checker : si primary_intent in INFORMATIVE_INTENTS → "information_node"
- Edge : information_node → final_response

### Prompt final_response_prompt.py
- Nouvelle section INFORMATION CONTEXT RULES (avant OUTPUT FORMAT)
- Règles par subtype (follow_up_place high/low confidence, weather live/général, booking_info, session_planning, factual)
- 2 nouveaux exemples (Example 6 follow_up_place, Example 7 factual)
- Nouvelle variable {information_context} dans INPUTS

### final_response_node.py
- Import json
- Extrait information_context depuis state
- Passe information_context_str = json.dumps(information_context) au prompt
