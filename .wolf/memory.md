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

## 2026-07-29 — Atlas Search dual-analyzer (VERSION 8)

### Problème résolu
`semantic_node` produit keywords camelCase EN (`culturalActivity`) mais `activities_collection` tags en FR (`culture`).
Filtre `$in` exact → 0 match. Solution : Atlas Search avec dual-analyzer.

### Index `activities_search`
- Syntax `multi` objet → QUERYABLE en ~25s sur M0
- Syntax array `[{type,analyzer},{type,analyzer}]` → FAILED sans message d'erreur (piège sur M0)
- Monitoring via `col.aggregate([{"$listSearchIndexes": {}}])` (pymongo 3.12 compatible)
- Commande création : `db.command({"createSearchIndexes": "activities_collection", "indexes": [...]})`

### Matching cross-langue
- `culture` (FR tag) → lucene.french → stem `cultur`
- `culturalActivity` → split → `cultural` → lucene.english → stem `cultur` → MATCH
- `adventure` (EN query) ↔ `aventure` (FR tag) : edit dist = 1 → fuzzy:1 → MATCH

### `_normalize_keywords(keywords)` — ajouté dans mongodb_activity_service.py
```python
kw = kw.replace("_", " ")
kw = re.sub(r"([a-z])([A-Z])", r"\1 \2", kw)
tokens.extend(kw.lower().split())
```
Transforme `["culturalActivity","outdoor_activity"]` → `"cultural activity outdoor"`

### 3-level fallback chain dans get_candidates()
L1: Atlas Search `$search` → L2: filtre classique `col.find()` → L3: destination seule

### session_bootstrap.py fix USER NATIF
`user_id` absent retournait error dict → maintenant retourne native state correctement
