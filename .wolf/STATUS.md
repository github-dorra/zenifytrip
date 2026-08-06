# Wolf Status

## ✅ Sprint 1 (completed — session précédente)
Redis SessionManager + GraphState fields (last_candidates, information_context) + main.py integration

## ✅ Sprint 2 (completed — session 2026-07-28)
Pipeline informatif : information_node + routing builder.py + final_response_prompt.py + final_response_node.py

### Ce qui a été fait
- `app/nodes/conversation/information_node.py` — créé (Python rule-based, 0 LLM, 5 subtypes)
- `app/graph/builder.py` — INFORMATIVE_INTENTS + route → information_node + add_node + edges
- `app/prompts/final_response_prompt.py` — section INFORMATION CONTEXT RULES + 2 exemples + {information_context} input
- `app/nodes/conversation/final_response_node.py` — extrait information_context, le passe au prompt en JSON string

## ✅ Sprint 2E (completed — session 2026-07-28)
Tests 7/7 PASS — 5 subtypes (weather, booking_info, follow_up_place, session_planning, factual) validés

## ✅ Gemini Migration (completed — session 2026-07-28)
- definitions.py → provider="gemini", model="gemini-3.1-flash-lite" (15 RPM, 250K TPM)
- llm_service.py → call_gemini_llm avec response_format + fallback Groq auto sur 429
- Clé AI Studio : projet zenify (gen-lang-client-0242501178)
- gemini-2.0-flash avait quota=0 → migré vers gemini-3.1-flash-lite (testé OK, provider=gemini natif)

## ✅ Phase 5 (completed — 2026-07-29)
feedback_logger_node + profile_writer_node + ranking cross-session
- feedback_logger : mine conversation_history → liked/rejected types (session_memory)
- profile_writer  : persiste interactions:{traveller_id} Redis TTL 90j, merge cumulatif
- ranking_node    : lit cross-session Redis → ranked_score=0 pour types rejetés (activity)
- settings.py     : INTERACTIONS_REDIS_PREFIX + INTERACTIONS_REDIS_TTL_SECONDS
- Testé 3/3 PASS, commité 9f83736

## ✅ Atlas Search cross-langue (completed — 2026-07-29)
- `mongodb_activity_service.py` — $in remplacé par $search dual-analyzer (commit 8e92b57)
- `session_bootstrap.py` — fix USER NATIF (même commit)
- Index `activities_search` recréé syntax `multi` objet (array syntax FAILED sur M0)
- `_normalize_keywords()` : camelCase splitting avant query Atlas Search
- 3/3 tests PASS : cultural/heritage/beach/outdoor → matching cross-langue FR↔EN
- CLAUDE.md → VERSION 8 ajouté

## ✅ Orchestrateur Intelligent (completed — 2026-07-31)
Hybrid orchestrator (règles 80% + LLM Gemini si voyage actif / repas inclus / dernier jour)

### Fichiers modifiés / créés
- `app/prompts/recommendation/orchestrator_prompt.py` — prompt context-aware (meal_plan, skeleton, booking_anchors, 4 exemples)
- `app/schemas/orchestrator_schema.py` — OrchestratorOutput Pydantic (requested_services, constraints_per_service, reasoning)
- `app/config/definitions.py` — ORCHESTRATOR_CONFIG (gemini, temp=0.0, max_tokens=600)
- `app/graph/state.py` — orchestrator_constraints + orchestrator_reasoning dans TypedDict + build_initial_state()
- `app/nodes/recommendation/orchestration/orchestrator_node.py` — full rewrite hybrid (_needs_llm, _rules_decision, _llm_decision)
- `app/nodes/recommendation/domain/activity_node.py` — filtres post-fetch (max_duration_hours, exclude_activity_ids, exclude_types)
- `app/nodes/recommendation/domain/restaurant_node.py` — meal_slot override dans _resolve_establishment_types (priorité 2)
- `app/graph/builder.py` — comment [tech] → [LLM] Gemini 3.1 Flash Lite

### Comportement
- USER NATIF / intent simple → chemin règles (0 token LLM)
- USER RÉEL voyage en cours (HB/AI/FB, dernier jour, anchors) → LLM single-shot avec contraintes par service
- Fallback automatique règles si LLM échoue (try/except)

### Tests (2026-07-31)
4/4 PASS — `python -m app.test_orchestrator`
- S1 HB dernier jour : LLM calcule 2h fenêtre, max_duration_hours=2.0, exclude_types=[full_day,excursion], nearby_hotel=true
- S2 AI jour normal : restaurant_node absent (tout inclus)
- S3 USER NATIF : chemin règles, 0 LLM
- S4 AI + resto explicite : optional_experience=true, meal_slot=dinner

## ✅ Agent 3 — InformativeResponseNode (2026-07-31)
- `app/nodes/conversation/informative_response_node.py` — Agent 3 (Gemini, prompt expert)
- `app/prompts/informative_response_prompt.py` — prompt spécialisé 6 subtypes
- `app/config/definitions.py` — INFORMATIVE_RESPONSE_CONFIG
- `app/config/settings.py` — TAVILY_TIMEOUT_SECONDS + TAVILY_MAX_RESULTS
- `app/nodes/conversation/information_node.py` — _DYNAMIC_KW + _resolve_dynamic_factual + cache session
- `app/graph/builder.py` — information_node → informative_response → END (était → final_response)
- Flux : travel_question/booking_question → information_node (rule-based) → informative_response (LLM Agent 3) → END
- Tavily : dynamic_factual (visa/prix/horaires/événements), cache session, fallback LLM si no key/timeout/0 results
- Compilation : 27 nodes OK

## ✅ VERSION 10 — Agent 3 + Fix vol (session 2026-07-31)
- `information_node.py` — `_BOOKING_KW` étendu vols, `_profile_flights()`, `_extract_flight_info()` normalisé, `_resolve_booking_info()` normalisé, `_detect_subtype()` + `profile_data`
- `builder.py` — `_BOOKING_FORCE_KW` guard + `route_after_context_merge` + edge `information_node → informative_response → END`
- `informative_response_prompt.py` — section booking_info vol + exemple TU309
- `CLAUDE.md` — VERSION 10 documentée (3 agents, Tavily, chemin normalisé vols, topologie 27 nodes)

## ✅ Déploiement Hetzner + Moteur Inférence Ollama (session hebergement)
Staging complet sur Hetzner CX32 avec Ollama comme moteur d'inférence local.

### Fichiers créés / modifiés
- `app/api.py` — FastAPI wrapper autour du pipeline LangGraph (POST /chat, GET /health)
- `app/config/llm_service.py` — fix Ollama URL (localhost:11434), init sans auth, 3ème fallback Gemini→Groq→Ollama
- `Dockerfile` — python:3.13-slim, fastapi + uvicorn, 2 workers
- `docker-compose.yml` — services: app + ollama (llama3.1:8b) + redis + nginx
- `nginx/default.conf` — reverse proxy, timeout 120s pour pipeline LangGraph
- `.env.example` — template complet toutes variables d'env
- `deploy.sh` — script step-by-step Ubuntu 22.04 Hetzner CX32

### Chaîne LLM déployée
Gemini (principal, 1500 req/j) → Groq (fallback 429) → Ollama llama3.1:8b (fallback final, moteur local)

### Justification modèle Ollama
llama3.1:8b retenu (vs llama3.2:3b initial) pour maintenir la précision et la crédibilité
de l'app. ~4.5 GB RAM, CPU-only sur CX32, ~8-12s par requête — acceptable comme fallback d'urgence.

## ✅ Sprint Scoring (2026-08-06) — 6 bugs scoring corrigés
- P0 da16d81 : `user_score` absent RestaurantCandidate → restaurants MongoDB filtrés → model_validator sync
- P1 b2bab5e : data_merger lisait `score` avant `user_score` → chaîne user_score>match_score>score
- P2 181a927 : 0.7/0.3 hardcodés dans 4 services → import USER_SCORE_WEIGHT/BUSINESS_SCORE_WEIGHT
- P3 dffb486 : SerpAPI business_score=0.50 au lieu de 0.20 → valeur explicite + mapping ranking_node
- P4 40f778f : _rating_confiance non-monotone (2 avis < 0 avis) → max(0.5, ...)
- P5 9995650 : budget_soft_match binaire → décroissance linéaire 0-4

## ✅ Bugs Connus CLAUDE.md — tous résolus
- main.py état incomplet : build_initial_state() déjà utilisé, pas de state.update(result)
- final_response_node.py : intent_result None-safety + constraints correct path

## ✅ Scoring V2 Implémenté (2026-08-06)
3 améliorations commitées — commits `5f403da` (①②) et `b090953` (③) :

### ① Proximity score restaurant (commit 5f403da)
- `_proximity_score(distance_km)` : 1.0 à 0km, décroissance linéaire, plancher 0.1 à RESTAURANT_PROXIMITY_MAX_KM=5km
- `RESTAURANT_PROXIMITY_MAX_KM` dans settings.py
- Formule 6 termes : rel(35%) + rating(25%) + zone(10%) + budget(10%) + proximity(10%) + hours(10%)

### ② Horaires d'ouverture restaurant (commit 5f403da)
- `_hours_score(opening_hours_text, request_hour)` : regex _TIME_RE sur formats FR/EN tunisiens
- `request_hour` injecté par restaurant_node via `datetime.now().hour`, désactivé si day_skeleton présent
- Flux : restaurant_node → search_strategy["request_hour"] → restaurant_service → MongoRestaurantService.search()

### ③ Weather factor activités (commit b090953)
- `_weather_factor(candidate, weather_context)` dans ranking_node
- nature/adventure → outdoor_score ; culture/relax → indoor_score ; city_experience → moyenne
- Interpolation [WEATHER_FACTOR_MIN=0.70, 1.0] — jamais éliminatoire
- Formule : ranked_score = user_score × business_boost × avail_factor × weather_factor

## 🚀 Prochaine quête
- Finalisation rapport PFE
- Tests E2E complets (8 scénarios) pour valider la chaîne scoring corrigée
- Tester "quel est le prix d'entrée au Bardo ?" (dynamic_factual + Tavily si TAVILY_API_KEY configurée)
