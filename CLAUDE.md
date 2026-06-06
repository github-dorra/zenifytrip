# zenifyTrip — Système de Recommandation Touristique

## Objectif du Projet

### Présentation Générale
ZenifyTrip est un **système intelligent de recommandation touristique** basé sur une architecture multi-agents orchestrée par des modèles de langage avancés (LLM). Il est intégré sous forme d'**assistant conversationnel** dans une application touristique existante appartenant à une agence de voyage.

L'utilisateur décrit ses besoins en langage naturel (français en priorité, aussi EN/ES/DE/AR). Le système classifie l'intention, extrait les contraintes, détecte les informations manquantes et génère une réponse conversationnelle personnalisée.

Construit sur **LangGraph** (pipeline de 17 étapes, 5 phases), avec **Groq** comme LLM principal et **Ollama Cloud** pour les agents lourds. Le système fonctionne selon 3 modes : **EXPLORATORY** (user natif, peu de détails), **PRECISE_PLAN** (destination + durée connues), **BOOKING** (réservation immédiate via APIs internes agence). L'architecture repose sur 4 couches : collecte de données, services spécialisés, validation Pydantic, et graphe multi-agents LangGraph.

### Objectif Principal
Fournir des recommandations **personnalisées, contextuelles et dynamiques** tout en servant un objectif commercial réel.

> Le système recommande **EN PRIORITÉ** les offres disponibles dans le booking interne de l'agence.
> Si indisponible en interne → recommandation depuis sources externes.

### Ce que le Système Peut Faire
- Recommander des destinations touristiques
- Proposer des activités personnalisées
- Générer des plans de journée
- Construire des itinéraires complets
- Suggérer des périodes idéales pour voyager
- Recommander des restaurants et événements
- Adapter les recommandations selon le contexte réel du voyageur

### Innovation Principale du Projet
La vraie innovation de ZenifyTrip est la combinaison de :

| Dimension | Description |
|-----------|-------------|
| **Business Recommendation** | Priorité commerciale agence — offres internes avant sources externes |
| **Contextual AI** | Météo, localisation, saison intégrés dans les recommandations |
| **Multi-Agent Orchestration** | Planner et Orchestrator séparés — pipeline de 17 étapes |
| **Conversational Planning** | Chatbot LLM naturel — dialogue progressif et affinement |

> Le système n'est pas seulement un assistant IA. C'est un **moteur commercial intelligent** pour une agence de voyage.

**Score final de recommandation :**
```
Score = 70% user_score + 30% business_score
         └── personnalisé        └── orienté commercialement
```

> Projet de stage chez ZenifyTrip. Le rapport académique se trouve dans `../rapport/main.docx` (style Times New Roman, français académique, structure par chapitres — voir `rapport/CLAUDE.md`).

## Stack Technique
| Composant | Version / Détail |
|-----------|-----------------|
| Python | 3.13 — venv actif : **venv1** |
| LangGraph | 1.1.8 — orchestre le graphe d'agents (StateGraph, 17 étapes) |
| LangChain Core | 1.3.0 — abstractions de base |
| Groq API | LLM principal (`llama-3.3-70b-versatile`) — gratuit, rapide |
| Ollama Cloud | LLM secondaire (`gpt-oss:120b`, `gemini-3-flash-preview`) — ~20$/mois, agents lourds |
| Pydantic v2 | Validation stricte des données — contrats entre agents |
| python-dotenv | Chargement des variables d'environnement |

## Lancer l'Application
```bash
# Depuis la racine du projet, avec venv1 activé
python -m app.main
```
L'app est une boucle CLI. L'utilisateur tape des messages, Ctrl+C pour quitter.

## Architecture : Graphe LangGraph

### VERSION 1 — Phase 1 validée ✓ (pipeline actuel fonctionnel)

> Validée et testée le 2026-05-24. 7 scénarios couverts : USER RÉEL, USER NATIF, greeting, travel question, booking, unsupported. `errors: []` sur tous les cas.

```
START ──→ [greeting]          ──→ [intent_classifier] ──────────────→ [context_merge]
      └──→ [session_bootstrap] ──→ [profile_loader]   ──────────────→ [context_merge]
                                                                            │
                                                               [clarification_checker]
                                                                            │
                                                                    [final_response]
                                                                            │
                                                                           END
```

**Nodes implémentés et validés :**

| Node | Type | Rôle | Statut |
|------|------|------|--------|
| `greeting` | Python technique | Normalise le message (`strip().lower()`) | ✓ |
| `session_bootstrap` | Python technique | Résout `travellerId` via API, assigne `user_type` + `suggestion_mode` initial | ✓ |
| `intent_classifier` | LLM Groq | Classifie intent, extrait contraintes, détecte langue | ✓ |
| `profile_loader` | API interne | Charge profil voyageur structuré depuis API staging | ✓ |
| `context_merger` | Python technique | Fusionne intent + profil → `merged_context` enrichi | ✓ |
| `clarification_checker` | Rule-based | Détecte champs manquants, détermine mode, respecte `user_type` | ✓ |
| `final_response` | LLM Ollama | Génère réponse conversationnelle naturelle | ✓ |

**Logique USER RÉEL / USER NATIF (implémentée dans `session_bootstrap` + `clarification_checker`) :**

| | USER RÉEL (`travellerId` résolu) | USER NATIF (`travellerId` = null) |
|-|----------------------------------|-----------------------------------|
| `user_type` | `"real"` | `"native"` |
| `suggestion_mode` initial | `"precise_plan"` | `"exploratory"` |
| Mode minimum garanti | `"semi_exploratory"` (jamais `exploratory`) | aucun plancher |

**Bugs corrigés dans cette version :**
- `ProfileService` async → synchrone (`requests`)
- `context_merger` retournait `state` entier → `{"merged_context": merged}`
- `main.py` clé `constraints` incorrecte → `intent_result["constraints"]`
- `profile_loader safe_get` incomplet → ajout du `key` argument
- `travellerId` clé incohérente → uniformisé partout
- `greeting_node` appelait `bootstrap_session` en double → supprimé
- Fan-in LangGraph mal synchronisé → `START` node avec deux branches parallèles
- `hotel_stars` crash `None > int` → regex + `or 0`
- Tags lus depuis mauvaise source dans `context_merger` → `profile_data["tags"]`
- `reponse_schema` Literal trop strict → `field_validator(mode="before")` normalisation

### Graphe cible — pipeline complet 17 étapes
```
Entrée Utilisateur
        │ (fan-out)                                   PHASE 1 : COMPRÉHENSION
        ├─────────────────────────────────┐
   [greeting]                   [session_bootstrap]
   ← query uniquement            ← findTravellerId → USER RÉEL / USER NATIF
        │                                 │
        └───────────────┬─────────────────┘
                        │ (fan-out)
                        ├───────────────────────┐
              [intent_classifier]    [profile_loader]       ← en parallèle
                        └──────────┬────────────┘
                                   ▼
                          [context_merge] → [clarification_checker]
                                   │
                          [semantic_node] → [availability_checker]  PHASE 2 : ROUTAGE CONDITIONNEL + SEMANTIC
                                   │
                           [orchestrator]                            PHASE 3 : ORCHESTRATION
                                   │ (fan-out selon intent)
                ┌──────┬───────┬────────┐
            [hotel] [flight] [resto] [activity]                  PHASE 4 : RECOMMANDATION
                └──────┴───────┴────────┘
                                   │
            [constraint_validator] → [data_merger] → [ranking]      PHASE 4 : RANKING
                                   │
                 [day_planner] → [recommendation_composer]
                                   │
                          [final_response]                           PHASE 4 : RÉPONSE
                                   │
               [feedback_logger] → [profile_writer]              PHASE 5 : APPRENTISSAGE
                                   │
                                  END
```

> Routage conditionnel commenté dans `builder.py` — actuellement `clarification_checker` va toujours vers `final_response`.

## Structure des Répertoires
```
app/
├── main.py                          # Point d'entrée CLI — boucle de conversation
├── config/settings.py               # Chargement des variables d'env via dotenv
├── list_models.py                   # Utilitaire : lister les modèles disponibles
├── test.py / test_ollama.py         # Scripts de test manuels
│
├── graph/
│   ├── state.py                     # GraphState TypedDict + build_initial_state()
│   ├── builder.py                   # Topologie du graphe + fonctions de routage
│   └── routing.py                   # (vide — le routage est dans builder.py)
│
├── nodes/
│   ├── core/
│   │   ├── Base_node.py             # BaseNode ABC + NodeConfig dataclass
│   │   └── session_bootstrap.py     # Récupère traveller_id depuis user_id via API
│   │
│   ├── conversation/
│   │   ├── greeting_node.py         # Reçoit et normalise le query — en parallèle avec session_bootstrap
│   │   └── final_response_node.py   # Formateur de réponse (LLM Groq)
│   │
│   ├── comprehension/
│   │   ├── intent_classifier_node.py    # LLM : classifie l'intent + extrait les contraintes
│   │   └── clarification_checker_node.py  # Rule-based : détecte les champs manquants
│   │
│   ├── user_profile/
│   │   ├── profile_loader_node.py       # Récupère le profil voyageur depuis l'API
│   │   ├── profile_cache_reader_node.py # Lecture profil depuis le cache
│   │   └── profile_writer_node.py       # Écriture/mise à jour du profil en cache
│   │
│   ├── merge/
│   │   └── context_merger_node.py   # Fusionne intent_result + profile_data → merged_context
│   │
│   ├── recommendation/
│   │   ├── orchestration/
│   │   │   └── orchestrator_node.py     # (vide — à implémenter)
│   │   ├── domain/
│   │   │   ├── hotel_node.py            # (vide — à implémenter)
│   │   │   ├── flight_node.py           # (vide — à implémenter)
│   │   │   ├── restaurant_node.py       # (vide — à implémenter)
│   │   │   └── activity_node.py         # (vide — à implémenter)
│   │   ├── postprocessing/
│   │   │   ├── constraint_validator_node.py
│   │   │   ├── data_merger_node.py
│   │   │   ├── ranking_node.py
│   │   │   ├── day_planner_node.py
│   │   │   └── recommendation_composer_node.py
│   │   └── context/
│   │       ├── semantic_node.py
│   │       └── availability_checker_node.py
│   │
│   ├── Logistics/
│   │   ├── wearth_node.py           # Informations météo (OpenWeather)
│   │   └── maps_node.py             # Intégration Google Maps
│   │
│   ├── shared/
│   │   ├── error_handler_node.py
│   │   └── feedback_logger_node.py
│   │
│   ├── utility/
│   │   └── json_parser.py           # parse_json_safely()
│   │
│   └── definitions.py               # Instances NodeConfig pour chaque agent LLM
│
├── prompts/
│   ├── comprehension/intent_classifier_prompt.py
│   ├── conversation/
│   │   ├── greeting_prompt.py
│   │   └── final_response_prompt.py
│   └── recommendation/
│       ├── orchestrator_prompt.py
│       └── semantic_prompt.py
│
├── schemas/
│   ├── intent_schema.py         # TravelConstraints, IntentClassifierOutput, PrimaryIntent
│   ├── reponse_schema.py        # ResponseAgentOutput
│   ├── profile_schema.py
│   ├── recommendation_schema.py
│   ├── semantic_schema.py
│   ├── weather_schema.py
│   └── map_schema.py
│
└── services/
    ├── llm_service.py           # call_llm() → dispatche vers call_groq_llm ou call_ollama_llm
    ├── profile_service.py       # ProfileService.get_traveller_profile()
    ├── weather_service.py
    ├── Map_service.py
    ├── cache_service.py         # Cache en mémoire (clé SHA-256)
    ├── availability_service.py
    ├── hotel_service.py
    ├── flight_service.py
    ├── restaurant_service.py
    ├── activity_service.py
    ├── internal_api_service.py
    ├── logging_service.py
    └── baseClient/
        ├── base.py              # Client HTTP de base
        └── WeatherClient.py     # Client météo spécialisé
```

## Patterns de Conception Clés

### BaseNode (`nodes/core/Base_node.py`)
Toute node hérite de `BaseNode` et implémente `run(state) -> dict`. `__call__` enveloppe `run` avec :
- Métriques de timing (`node_metrics` list, `operator.add` pour append sécurisé)
- Gestion d'erreurs + fallback automatique
- Cache optionnel (clé = SHA-256 de prompt + modèle + paramètres)
- Validation Pydantic optionnelle entrée/sortie (`input_schema`, `output_schema`)
- Score de confiance (`calculate_confidence()` — formule pondérée 40/25/20/15)

**Règle absolue** : les nodes ne retournent **que les clés qu'elles mettent à jour** — jamais `{**state, ...}`.

### NodeConfig (`nodes/core/Base_node.py`)
Dataclass définissant le contrat d'un node LLM :
```python
@dataclass
class NodeConfig:
    name: str
    node_type: str      # "technical" | "llm_agent" | "tool_node" | "conversation"
    provider: str       # "groq" | "ollama"
    model: Optional[str]
    temperature: float
    max_tokens: int
    response_format: Optional[Any]
    cache_enabled: bool
    cache_ttl_seconds: int
```

### GraphState (`graph/state.py`)
TypedDict central — source unique de vérité. Champs principaux :

| Catégorie | Champs |
|-----------|--------|
| Session | `session_id`, `user_id`, `traveller_id` |
| Message | `user_message`, `normalized_message`, `conversation_history` |
| Intent NLU | `intent_result` → `{primary_intent, secondary_intents, action_type, constraints, language, confidence}` |
| Profil | `profile_data` |
| Contexte fusionné | `merged_context` |
| Clarification | `missing_required`, `missing_optional`, `blocking_fields`, `suggestion_mode`, `decision_confidence`, `clarification_needed`, `clarification_question`, `clarification_focus`, `clarification_type` |
| Routage | `next_action` |
| Disponibilité | `traveller_available`, `availability_result` |
| Météo | `weather_context`, `weather` |
| Sémantique | `semantic_keywords`, `semantic_tags`, `semantic_query` |
| Recommandations | `hotel_candidates`, `restaurant_candidates`, `activity_candidates`, `flight_candidates`, `candidates`, `ranked_results`, `recommendations`, `itinerary` |
| Réponse | `final_answer` |
| Technique | `errors` (`Annotated[List, operator.add]`), `node_metrics` (`Annotated[List, operator.add]`) |

### Configurations LLM (`nodes/definitions.py`)
| Config | Provider | Modèle | Usage |
|--------|----------|--------|-------|
| `INTENT_CLASSIFIER_CONFIG` | groq | llama-3.3-70b-versatile | Classification d'intention |
| `SEMANTIC_CONFIG` | ollama | gemini-3-flash-preview | Extraction sémantique |
| `ORCHESTRATOR_CONFIG` | ollama | gpt-oss:120b | Orchestration recommandations |
| `RANKING_CONFIG` | ollama | gpt-oss:120b | Classement des résultats |
| `DAY_PLANNER_CONFIG` | ollama | gpt-oss:120b | Planification journalière |
| `RESPONSE_CONFIG` | ollama | gpt-oss:120b | Formatage réponse (non utilisé, FinalResponseNode utilise Groq) |

### Service LLM (`services/llm_service.py`)
`call_llm(prompt, model, provider, ...)` dispatche vers `call_groq_llm` ou `call_ollama_llm`. Client Ollama initialisé à l'import — **plante si `OLLAMA_API_KEY` est None** (voir bugs connus).

## APIs Externes
| Service | Variable d'env | Auth |
|---------|----------------|------|
| Lookup voyageur | `TRAVELER_API_URL/{user_id}` | Bearer JWT (`API_KEY`) |
| Profil voyageur | `TRAVELLER_MANAGEMENT/{traveller_id}` | Bearer JWT |
| OpenWeather | `OPENWEATHER_BASE_URL` | `OPENWEATHER_API_KEY` |
| Google Maps | `GOOGLE_MAPS_BASE_URL` | `GOOGLE_MAPS_API_KEY` |
| Groq LLM | SDK Groq | `GROQ_API_KEY` |
| Ollama LLM | `OLLAMA_BASE_URL` | Bearer `OLLAMA_API_KEY` |

## Schémas d'Intention (`schemas/intent_schema.py`)

```
PrimaryIntent  : greeting | flight_recommendation | accommodation_recommendation
                 restaurant_recommendation | activity_recommendation | day_planning
                 trip_package_recommendation | travel_question | profile_update
                 booking_question | feedback | unsupported

ActionType     : recommendation | booking | information | profile_update | none
BudgetLevel    : low | medium | luxury
LanguageCode   : en | fr | es | de | ar
```

`TravelConstraints` contient : `origin`, `destination`, `start_date`, `end_date`, `duration_days`, `travelers`, `budget_level`, `interests`, `activity_preferences`, `restaurant_preferences`, `accommodation_preferences`, `flight_preferences`.

## Logique de Clarification (`nodes/comprehension/clarification_checker_node.py`)
Node rule-based (sans LLM). Évalue les champs requis selon `action_type` :
- `booking` → `[origin, destination, start_date, travelers]`
- `recommendation` → `[destination]`
- `information` → `[]`

Décision :
- 0 champs bloquants → `precise_plan`, confidence `high`, `next_action = continue`
- 1 champ bloquant → `semi_exploratory`, confidence `medium`, `next_action = ask_clarification`
- 2+ champs bloquants → `exploratory`, confidence `low`, `next_action = ask_clarification`

## Flux Intent → Action
```
primary_intent                     → suggestion_mode      → prochaine étape
────────────────────────────────────────────────────────────────────────────
greeting / unsupported             → (pas de clarification) → final_response
travel_question                    → exploratory/semi/precise → final_response
flight_recommendation              → vérif. contraintes    → flight_node (TODO)
accommodation_recommendation       → vérif. contraintes    → hotel_node (TODO)
restaurant_recommendation          → vérif. contraintes    → restaurant_node (TODO)
activity_recommendation            → vérif. contraintes    → activity_node (TODO)
day_planning                       → vérif. contraintes    → day_planner (TODO)
trip_package_recommendation        → vérif. contraintes    → orchestrator (TODO)
```

## Deux Types d'Utilisateurs

La distinction se fait via l'API interne `findTravellerId(user_id)` :

| | USER RÉEL | USER NATIF |
|-|-----------|------------|
| **Résultat API** | `traveller_id` retourné | `null` / 404 retourné |
| **Profil** | Enrichi — historique, préférences, voyages passés | Minimal ou vide |
| **Contexte voyage** | Connu : destination, hôtel, dates (voucher actif) | Inconnu |
| **Mode par défaut** | `PRECISE_PLAN` ou `BOOKING` | `EXPLORATORY` |
| **Clarification** | Moins nécessaire — contexte déjà disponible | Questions progressives jusqu'à affiner |
| **Recommandations** | Ciblées : activités, restaurants, day planning | Larges, puis affinement progressif |

**USER RÉEL** (traveller_id retourné) :
- Possède une réservation active (voucher)
- Contexte voyage connu : destination, hôtel, dates
- Profil voyageur enrichi et historique disponible
- Recommandations ciblées : activités, restaurants, day planning
- Moins de clarification nécessaire

**USER NATIF** (null / 404 retourné) :
- A installé l'app sans réservation active
- Profil minimal ou vide
- Mode `EXPLORATORY` par défaut
- Le système pose des questions progressives
- Recommandations larges puis affinement progressif

## 3 Modes de Recommandation

| Mode | Déclencheur typique | Comportement |
|------|---------------------|--------------|
| **EXPLORATORY** | User NATIF, peu de détails fournis | Aucun blocage sur champs manquants — propose plusieurs options larges et variées |
| **PRECISE_PLAN** | Destination et durée connues | Planning détaillé — dates optionnelles mais recommandées |
| **BOOKING** | User RÉEL, veut réserver maintenant | Dates et disponibilité obligatoires — APIs internes agence en priorité absolue |

**EXPLORATORY** :
- User veut des idées, peu de détails fournis
- Aucun blocage sur champs manquants
- Propose plusieurs options larges
- Typique : USER NATIF

**PRECISE_PLAN** :
- User veut un planning détaillé
- Destination et durée connues
- Dates optionnelles mais recommandées

**BOOKING** :
- User veut réserver maintenant
- Dates et disponibilité obligatoires
- APIs internes agence en priorité absolue

## Pipeline Détaillé — 17 Étapes

### Structure Logique
```
INPUT
  ↓
Compréhension          (greeting, session bootstrap, intent classifier, profile loader)
  ↓
Enrichissement contexte (context merge, clarification checker)
  ↓
Planification           (semantic agent, availability checker)
  ↓
Orchestration           (orchestrator)
  ↓
Recommandation          (hotel, flight, restaurant, activity — en parallèle)
  ↓
Ranking business + user (constraint validator, data merger, ranking)
  ↓
Réponse conversationnelle (day planner, recommendation composer, final response)
  ↓
Apprentissage utilisateur (feedback logger, profile writer)
```

### Étapes par Phase

**PHASE 1 — COMPRÉHENSION**

| Étape | Node | Type | Rôle |
|-------|------|------|------|
| 1 | `greeting_node` | LLM léger | Réception requête, initialisation session conversationnelle |
| 2 | `session_bootstrap` | Python technique | Appelle `findTravellerId(user_id)` → résout le `traveller_id` |
| 3 | `intent_classifier_node` | LLM (Groq) | Classifie l'intent + extrait les contraintes — en parallèle avec étape 4 |
| 4 | `profile_loader_node` | API interne | Charge le profil voyageur complet — en parallèle avec étape 3 |
| 5 | `context_merger_node` | Python technique | Fusionne intent_result + profile_data → merged_context |
| 6 | `clarification_checker_node` | Python rule-based | Détecte champs obligatoires manquants, détermine le mode |

**Étapes 1 + 2 — Greeting Node + Session Bootstrap Node** `[parallèle — fan-out dès l'entrée]`

- `greeting_node` et `session_bootstrap` s'exécutent **en parallèle** dès la réception du message

**Étape 1 — Greeting Node** `[LLM léger]`
- Reçoit et normalise le query utilisateur uniquement
- Initialise la session conversationnelle
- Ne fait PAS de résolution d'identité

**Étape 2 — Session Bootstrap Node** `[Python technique]`
- Récupère `user_id` depuis la session
- Appelle API interne `findTravellerId(user_id)`
- Retourne `traveller_id` → **USER RÉEL** : charge contexte voyage complet (destination, hôtel, dates, profil enrichi)
- Retourne `null`/404 → **USER NATIF** : profil vide, mode EXPLORATORY par défaut

**Étapes 3 + 4 — Intent & NLU Node + Profile Loader** `[parallèle]`
- Étape 3 : classifie l'intention principale, extrait les contraintes brutes, détecte la langue (FR/EN/ES/DE/AR)
- Étape 4 : charge le profil voyageur complet depuis l'API interne

---

**PHASE 2 — ENRICHISSEMENT CONTEXTE**

| Étape | Node | Type | Rôle |
|-------|------|------|------|
| 7 | `semantic_node` | LLM (Ollama) | Extrait keywords, tags, requête sémantique |
| 8 | `availability_checker_node` | API interne | Vérifie disponibilité voyageur et offres agence |

---

**PHASE 3 — ORCHESTRATION & RECOMMANDATION**

| Étape | Node | Type | Rôle |
|-------|------|------|------|
| 9 | `orchestrator_node` | LLM (Ollama) | Sélectionne les agents domaine à activer selon l'intent |
| 10 | `hotel_node` | API/Service | Candidats hébergement (TODO) |
| 11 | `flight_node` | API/Service | Candidats vols (TODO) |
| 12 | `restaurant_node` | API/Service | Candidats restaurants (TODO) |
| 13 | `activity_node` | API/Service | Candidats activités (TODO) |

---

**PHASE 4 — RANKING & RÉPONSE**

| Étape | Node | Type | Rôle |
|-------|------|------|------|
| 14 | `constraint_validator_node` + `data_merger_node` | Python | Valide et fusionne les candidats |
| 14b | `ranking_node` | LLM (Ollama) | Classe selon score = 70% user + 30% business |
| 14c | `day_planner_node` | LLM (Ollama) | Génère un itinéraire jour par jour — prend en compte horaires, distances, météo, budget |
| 14d | `recommendation_composer_node` | Python | Formate les recommandations finales |
| 15 | `final_response_node` | LLM (Groq) | Génère réponse naturelle (FR ou EN), inclut références de réservation si disponibles, style adapté au user_type |

---

**PHASE 5 — APPRENTISSAGE**

| Étape | Node | Type | Rôle |
|-------|------|------|------|
| 16 | `feedback_logger_node` | Python/DB | Extrait l'avis utilisateur — enregistre : aimé, ignoré, rejeté |
| 17 | `profile_writer_node` | API interne | Met à jour le profil selon feedback — enrichissement implicite et continu des préférences |

**Étape 16 — Feedback Logger Node** `[Python/DB]`
- Extrait l'avis utilisateur sur la recommandation
- Enregistre : aimé, ignoré, rejeté

**Étape 17 — Profile Writer Node** `[Python/API interne]`
- Met à jour le profil selon feedback
- Enrichit préférences pour futures recommandations
- Apprentissage implicite et continu

## Convention Visuelle des Nœuds (Figures/Diagrammes)
| Couleur | Type de nœud |
|---------|-------------|
| Bleu | LLM Node (appel au modèle de langage) |
| Vert | Python déterministe (rule-based, technique) |
| Orange | API / Service externe ou interne |
| Violet | Memory / Profile (lecture ou écriture profil) |

## Architecture en 4 Couches
```
Couche 1 — Collecte des données
  APIs internes agence + APIs externes + interactions utilisateur

Couche 2 — Services spécialisés
  weather_service, map_service, hotel_service,
  flight_service, restaurant_service, activity_service

Couche 3 — Validation et modélisation
  Schémas Pydantic pour chaque échange inter-agents

Couche 4 — Multi-agents LangGraph
  Pipeline complet des 17 étapes (StateGraph)
```

## Technologies
| Rôle | Technologie | Détail |
|------|------------|--------|
| LLM principal | Groq | llama-3.3-70b-versatile — gratuit, rapide (compréhension + réponse) |
| LLM secondaire | Ollama Cloud | gpt-oss:120b — ~20$/mois (orchestration, ranking, day planning) |
| Orchestration | LangGraph | StateGraph avec fan-out parallèle |
| Validation | Pydantic v2 | Contrats de données entre agents |
| APIs externes | OpenWeather, Google Maps, restaurants tiers | Météo, cartographie, offres |
| APIs internes | Booking agence, profil voyageur, findTravellerId | Réservations, profil enrichi |
| Langage | Python 3.13 | venv1 |

- **LLM** : Ollama Cloud ~20$/mois (`gpt-oss:120b`) + Groq gratuit (`llama-3.3-70b-versatile`)
- **Orchestration** : LangGraph (StateGraph)
- **Validation** : Pydantic v2
- **APIs externes** : OpenWeather, Google Maps, restaurants tiers
- **APIs internes** : booking agence, profil voyageur, `findTravellerId`
- **Langage** : Python 3.13

## Périmètre et Perspectives
- **Implémenté** : sous-graphe Recommendation — pipeline complet 17 étapes (architecture définie, nodes compréhension opérationnels)
- **Perspectives** :
  - Sous-graphe Travel Info (questions générales sur la Tunisie)
  - Sous-graphe Assistant Général

## Démarche de Création d'un Agent — À SUIVRE OBLIGATOIREMENT

Toute création d'un nouveau node dans ce projet doit suivre ces **6 étapes dans l'ordre**. Ne pas sauter d'étape.

---

### Étape 1 — Définir le NodeConfig

**Node LLM** → déclarer dans `app/nodes/definitions.py` :
```python
MY_NODE_CONFIG = NodeConfig(
    name="my_node",
    node_type="llm_agent",       # llm_agent | conversation | comprehension
    provider="groq",             # groq | ollama
    model="llama-3.3-70b-versatile",
    temperature=0.0,
    max_tokens=800,
    response_format="json",
    cache_enabled=True,
    cache_ttl_seconds=3600,
)
```

**Node technique** (rule-based, pas de LLM) → NodeConfig inline dans `__init__` :
```python
super().__init__(NodeConfig(
    name="my_node",
    node_type="technical",       # technical | tool_node
))
```

---

### Étape 2 — Définir le Schéma de Sortie Pydantic *(LLM uniquement)*

Créer dans `app/schemas/my_node_schema.py` :
```python
from pydantic import BaseModel, Field, field_validator
from typing import Optional, List

class MyNodeOutput(BaseModel):
    field1: str
    field2: Optional[int] = None
    confidence: float = 0.0

    @field_validator("confidence")
    @classmethod
    def clamp(cls, v):
        return max(0.0, min(float(v or 0), 1.0))
```

- Un schéma = un contrat entre ce node et le reste du pipeline
- Toujours ajouter `confidence` pour les nodes LLM
- Utiliser `field_validator` pour normaliser les valeurs invalides, jamais lever d'exception

---

### Étape 3 — Écrire le Prompt *(LLM uniquement)*

Créer dans `app/prompts/<phase>/my_node_prompt.py`.
Suivre le **Format Standard des Prompts** documenté ci-dessous (section dédiée).

- Double accolades `{{}}` pour les accolades JSON littérales (escape Python `.format()`)
- Variables entre `{accolades simples}` pour `.format()`
- Les inputs/variables **toujours en bas** du prompt
- Le prompt définit **UNE seule responsabilité** — ne pas mélanger plusieurs rôles

---

### Étape 4 — Implémenter la Classe Node

Créer dans `app/nodes/<phase>/my_node.py` :
```python
from typing import Dict, Any
from app.nodes.core.Base_node import BaseNode
from app.nodes.definitions import MY_NODE_CONFIG       # LLM node
from app.prompts.<phase>.my_node_prompt import MY_NODE_PROMPT
from app.schemas.my_node_schema import MyNodeOutput
from app.nodes.utility.json_parser import parse_json_safely

class MyNode(BaseNode):

    def __init__(self):
        super().__init__(MY_NODE_CONFIG)

    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:

        # 1. EXTRACTION SÉCURISÉE depuis le state
        my_input = state.get("my_key") or ""

        # 2. CONSTRUCTION DU PROMPT
        prompt = MY_NODE_PROMPT.format(variable1=my_input)

        # 3. APPEL LLM + PARSING
        try:
            response = self.call_llm(prompt=prompt)
            raw = response.get("content", "")
            data = parse_json_safely(raw)
            output = MyNodeOutput(**data)

        except Exception as e:
            self.logger.error(f"MyNode error: {e}")
            output = MyNodeOutput()   # fallback valeurs par défaut

        # 4. RETOURNER UNIQUEMENT LES CLÉS MISES À JOUR
        return {
            "my_output_key": output.model_dump(),
        }
```

**Règles absolues :**
- `run()` retourne **uniquement les clés qu'il met à jour** — jamais `{**state, ...}` ni l'état entier
- Toujours un bloc `try/except` avec fallback explicite
- Extraction depuis le state avec `.get()` + valeur par défaut — jamais accès direct `state["key"]`
- Node technique (sans LLM) : même structure, sans appel `self.call_llm()`

---

### Étape 5 — Ajouter les Clés de Sortie dans GraphState

Dans `app/graph/state.py`, ajouter les nouvelles clés produites par le node :
```python
class GraphState(TypedDict):
    # ... champs existants ...
    my_output_key: Optional[Dict[str, Any]]   # produit par MyNode
```

Et dans `build_initial_state()` :
```python
"my_output_key": None,
```

---

### Étape 6 — Enregistrer dans le Graphe

Dans `app/graph/builder.py` :
```python
from app.nodes.<phase>.my_node import MyNode

def build_graph():
    # ...
    graph.add_node("my_node", MyNode())
    graph.add_edge("previous_node", "my_node")
    graph.add_edge("my_node", "next_node")
    # ...
```

Pour un routage conditionnel :
```python
graph.add_conditional_edges(
    "my_node",
    route_function,
    {
        "path_a": "node_a",
        "path_b": "node_b",
    }
)
```

---

### Récapitulatif par Type de Node

| Étape | Node LLM | Node Technique |
|-------|----------|----------------|
| 1. NodeConfig | `definitions.py` | Inline dans `__init__` |
| 2. Schema Pydantic | `schemas/` — obligatoire | Non requis |
| 3. Prompt | `prompts/` — obligatoire | Non requis |
| 4. Classe Node | `nodes/` — hérite BaseNode | `nodes/` — hérite BaseNode |
| 5. GraphState | Ajouter clés de sortie | Ajouter clés de sortie |
| 6. Builder | `add_node` + `add_edge` | `add_node` + `add_edge` |

### Erreurs Fréquentes à Éviter

| Erreur | Correct |
|--------|---------|
| `return {**state, "key": val}` | `return {"key": val}` uniquement |
| `state["key"]` accès direct | `state.get("key", default)` |
| NodeConfig LLM inline | NodeConfig LLM dans `definitions.py` |
| Prompt sans format JSON strict | Toujours spécifier le format de sortie |
| Pas de fallback dans `run()` | Toujours un `try/except` avec valeur par défaut |
| Oublier d'ajouter la clé dans `GraphState` | Ajouter dans `state.py` ET `build_initial_state()` |

## Format Standard des Prompts d'Agent — À SUIVRE OBLIGATOIREMENT

Extrait et déduit des 4 prompts existants du projet (`intent_classifier`, `final_response`, `orchestrator`, `semantic`).

---

### Structure Complète du Prompt

```python
MY_NODE_PROMPT = """

[SECTION 1 — IDENTITÉ & RÔLE]          ← obligatoire, toujours en premier
You are [rôle précis] inside [contexte système].

[SECTION 2 — GOAL]                      ← obligatoire
GOAL
[objectif unique et précis de ce node — UNE seule responsabilité]
Ce que l'agent NE FAIT PAS (limites explicites).

[SECTION 3 — BACKSTORY]                 ← optionnel, enrichit le persona
BACKSTORY
You are a seasoned [domaine] expert with [N] years of experience...

[SECTION 4 — CONTEXT]                   ← pour agents recevant du contexte structuré
CONTEXT
You have access to:
  - variable_1 : description
  - variable_2 : description

[SECTION 5 — DOMAINES / INTENTS]        ← pour agents de classification/sémantique
INTENTS / DOMAINS
intent_name → domaine, keywords valides, ce qu'il NE faut PAS inclure

[SECTION 6 — RÈGLES MÉTIER]             ← obligatoire
CRITICAL RULES / RULES
1. Règle numérotée
2. ...
- Return ONLY valid JSON. No markdown. No explanation. No extra text.
- Use null for unknown values.
- confidence between 0 and 1.

[SECTION 7 — LOGIQUE DE DÉCISION]       ← pour agents de routage (greeting, orchestrator)
DECISION LOGIC / REASONING LOOP
STEP A — ANALYZE : ...
STEP B — PLAN    : ...
STEP C — DISPATCH: ...
STEP D — SUPERVISE: ...

[SECTION 8 — SUIVI D'ÉTAT]              ← orchestrator uniquement
STATE TRACKING
"status": "pending" | "running" | "done" | "failed" | "skipped"

[SECTION 9 — EDGE CASES & FALLBACK]     ← recommandé
EDGE CASES
- champ vide → comportement par défaut
- échec worker → switch fallback
- intent ambigu → traitement par défaut

[SECTION 10 — FORMAT DE SORTIE]         ← obligatoire
OUTPUT FORMAT / JSON FORMAT
{{
  "field1": "",
  "field2": null,
  "confidence": 0.0
}}

[SECTION 11 — EXEMPLES]                 ← obligatoire
EXAMPLES
Input:  "message utilisateur"
Output: {{ ... JSON complet ... }}
(minimum 3 exemples couvrant : cas nominal, cas limite, cas unsupported)

[SECTION 12 — INPUTS VARIABLES]         ← obligatoire, TOUJOURS EN BAS
LABEL 1:
{variable_1}

LABEL 2:
{variable_2}
"""
```

---

### Règles d'Or du Prompt

| Règle | Détail |
|-------|--------|
| `{{}}` pour JSON | Accolades littérales JSON → doubles accolades pour échapper `.format()` |
| `{}` pour variables | Variables Python injectées via `.format(variable=valeur)` |
| Inputs tout en bas | Les variables `{var}` sont **toujours à la fin** du prompt |
| Une responsabilité | Un prompt = un rôle = un output — jamais mélanger plusieurs agents |
| JSON strict | Toujours : `"Return ONLY valid JSON. No markdown. No explanation."` |
| Limites explicites | Écrire ce que l'agent **NE FAIT PAS** (`You DO NOT recommend...`) |
| Min 3 exemples | Couvrir : cas nominal + cas limite + cas `unsupported`/fallback |
| `null` pas `None` | Utiliser `null` dans le prompt JSON (syntaxe JSON, pas Python) |

---

### Sections Obligatoires vs Optionnelles

| Section | Obligatoire | Type de node |
|---------|-------------|--------------|
| Identité & Rôle | Oui | Tous |
| GOAL | Oui | Tous |
| BACKSTORY | Non | LLM avec persona fort (intent_classifier) |
| CONTEXT | Non | Nodes recevant un contexte structuré riche |
| DOMAINES / INTENTS | Non | Classification, sémantique |
| CRITICAL RULES | Oui | Tous |
| DECISION LOGIC | Non | Agents de routage (greeting, orchestrator) |
| STATE TRACKING | Non | Orchestrator uniquement |
| EDGE CASES | Recommandé | Tous |
| OUTPUT FORMAT JSON | Oui | Tous |
| EXAMPLES | Oui | Tous |
| INPUTS VARIABLES | Oui | Tous — toujours en bas |

---

### Conventions de Nommage

```
Variable  : MY_NODE_PROMPT  ou  MY_NODE_SYSTEM_PROMPT
Fichier   : app/prompts/<phase>/my_node_prompt.py
Import    : from app.prompts.<phase>.my_node_prompt import MY_NODE_PROMPT
Utilisation: prompt = MY_NODE_PROMPT.format(variable1=val1, variable2=val2)
```

---

### Exemple Minimal Conforme au Projet

```python
MY_NODE_PROMPT = """
You are a [rôle] inside a multi-agent travel recommendation system for Tunisia.

GOAL
[Objectif unique].
You do NOT [limite 1].
You do NOT [limite 2].

CRITICAL RULES
1. Return ONLY valid JSON. No markdown. No explanation. No extra text.
2. Use null for unknown values.
3. confidence must be between 0 and 1.

OUTPUT FORMAT:
{{
  "result": "",
  "confidence": 0.0
}}

EXAMPLES

Input: "exemple 1"
Output:
{{
  "result": "valeur nominale",
  "confidence": 0.9
}}

Input: "exemple limite"
Output:
{{
  "result": null,
  "confidence": 0.0
}}

USER INPUT:
{user_message}

CONTEXT:
{merged_context}
"""
```

## Endpoints API Interne — Cartographie Complète

> Testés le 2026-05-24 contre `https://api.staging.zenifytrip.com`.
> Auth : `Authorization: Bearer {API_KEY}` sur tous les endpoints.

### Base URL
```
BASE_URL = https://api.staging.zenifytrip.com
```

---

### Endpoints Fonctionnels (HTTP 200)

#### Voyageurs

| Méthode | Endpoint | Rôle | Utilisé dans |
|---------|----------|------|-------------|
| `GET` | `/api/travellers/UserId/{user_id}` | Résoudre `user_id` → `traveller_id` | `session_bootstrap` |
| `GET` | `/api/traveller-management` | Liste tous les voyageurs (paginé) | — |
| `GET` | `/api/traveller-management/{traveller_id}` | Profil complet d'un voyageur | `profile_loader` |
| `GET` | `/api/travellers` | Liste simplifiée des voyageurs | — |

**Réponse `/api/traveller-management/{traveller_id}` :**
```json
{
  "id", "firstName", "lastName", "title",
  "hasPartner", "childCount", "babyCount",
  "outboundDate", "returnDate",
  "tags", "travellerTags",
  "outboundFlight": {
    "flightNumber", "takeoffTime", "landingTime", "airTime",
    "takeoffAirport": { "name", "iataCode" },
    "landingAirport": { "name", "iataCode" }
  },
  "returnFlight": { ... },
  "accommodations": [{
    "hotel": { "name", "starsCount", "shortDescription", "address", "picture" },
    "countNights", "mealPlan", "roomType", "adultCount", "date", "status"
  }]
}
```

---

#### Hôtels

| Méthode | Endpoint | Rôle | Volume |
|---------|----------|------|--------|
| `GET` | `/api/hotels` | Liste tous les hôtels (paginé) | 746 hôtels |
| `GET` | `/api/hotels/{id}` | Détail d'un hôtel | — |

**Query params supportés :** `take`, `skip`

**Réponse `/api/hotels` :**
```json
{
  "inlineCount": 746,
  "results": [{
    "id", "name", "starsCount",
    "shortDescription", "longDescription",
    "picture", "address", "zoneId",
    "checkIn", "checkOut",
    "facilities", "themes", "tags",
    "externalId": [{ "source", "id" }]
  }]
}
```

---

#### Vols

| Méthode | Endpoint | Rôle | Volume |
|---------|----------|------|--------|
| `GET` | `/api/flights` | Liste tous les vols (paginé) | 272 vols |
| `GET` | `/api/flights/{id}` | Détail d'un vol | — |
| `GET` | `/api/airports` | Liste des aéroports | — |
| `GET` | `/api/airline-companies` | Compagnies aériennes | — |

**Réponse `/api/flights` :**
```json
{
  "inlineCount": 272,
  "results": [{
    "id", "type", "flightNumber", "normalizedNumber",
    "takeoffTime", "landingTime", "airTime",
    "takeoffAirportId", "landingAirportId",
    "takeoffAirport": { "name", "iataCode", "icaoCode" },
    "landingAirport": { "name", "iataCode" },
    "externalId": [{ "source", "id" }]
  }]
}
```

---

#### Activités et Bookings

| Méthode | Endpoint | Rôle | Volume |
|---------|----------|------|--------|
| `GET` | `/api/bookings` | Liste toutes les réservations d'activités | 141 bookings |
| `GET` | `/api/bookings/{id}` | Détail d'une réservation | — |
| `GET` | `/api/activities/{id}` | Détail d'une activité | via booking |
| `GET` | `/api/hotel-services` | Services par hôtel (spa, soins...) | 26 services |
| `GET` | `/api/tourist-guides` | Guides touristiques | 19 guides |
| `GET` | `/api/transfers` | Transferts | — |

> **Note** : `GET /api/activities` (liste) retourne HTTP 500 — erreur DB côté backend.
> Utiliser `/api/bookings` pour trouver les `activityId`, puis `/api/activities/{id}`.

**Réponse `/api/activities/{id}` :**
```json
{
  "id", "name",
  "outboundDate", "returnDate",
  "adultPrice", "childPrice", "babyPrice", "currency",
  "recurrenceWeekDays", "recurrenceStart", "recurrenceEnd",
  "maxParticipants", "registeredParticipants",
  "activityTemplateId", "parentActivityId"
}
```

**Réponse `/api/bookings` :**
```json
{
  "inlineCount": 141,
  "results": [{
    "id", "travellerId", "activityId", "hotelServiceId",
    "date", "adultCount", "childCount", "babyCount",
    "totalPrice", "currency",
    "status",
    "referenceContactHotelName",
    "traveller": { ... }
  }]
}
```

**Statuts booking possibles :** `Pending` | `Confirmed` | `Cancelled`

---

#### Géographie et Référentiels

| Méthode | Endpoint | Rôle |
|---------|----------|------|
| `GET` | `/api/zones` | Zones touristiques |
| `GET` | `/api/airports` | Aéroports (IATA, ICAO, description) |
| `GET` | `/api/airline-companies` | Compagnies aériennes |
| `GET` | `/api/transfers` | Transferts aéroport/hôtel |
| `GET` | `/api/users` | Utilisateurs de la plateforme |

---

### Endpoints Non Disponibles (501 / 500)

| Endpoint | Status | Impact sur le projet |
|----------|--------|---------------------|
| `GET /api/restaurants` | **501** | `restaurant_node` → source externe uniquement (Google Places / TripAdvisor) |
| `GET /api/activities` | **500** DB error | Fallback via `/api/bookings` → `/api/activities/{id}` |
| `GET /api/destinations` | 200 mais vide | Non utilisable |
| `/api/packages` | 501 | Non prioritaire |
| `/api/tags` | 501 | Non prioritaire |

---

### Variables d'Environnement (`.env`)

```bash
API_KEY=<JWT Bearer token>
TRAVELER_API_URL=https://api.staging.zenifytrip.com/api/travellers/UserId
TRAVELLER_MANAGEMENT=https://api.staging.zenifytrip.com/api/traveller-management
```

**Variables à ajouter pour les nouveaux services :**
```bash
INTERNAL_API_BASE=https://api.staging.zenifytrip.com
# Les endpoints /api/hotels, /api/flights, /api/bookings, /api/activities
# utilisent tous le même BASE_URL + API_KEY
```

---

### Mapping Services → Endpoints

| Service Python | Endpoint(s) utilisé(s) | Statut |
|----------------|------------------------|--------|
| `session_bootstrap.py` | `GET /api/travellers/UserId/{user_id}` | ✅ Implémenté |
| `profile_service.py` | `GET /api/traveller-management/{traveller_id}` | ✅ Implémenté (bug async) |
| `hotel_service.py` | `GET /api/hotels` + `GET /api/hotel-services` + `GET /api/zones` | ✅ Implémenté |
| `flight_service.py` | `GET /api/flights` + `GET /api/airports` | ❌ À implémenter |
| `activity_service.py` | `GET /api/bookings` + `GET /api/activities/{id}` | ❌ À implémenter |
| `restaurant_service.py` | Aucun endpoint interne — source externe | ❌ À implémenter |
| `availability_service.py` | `GET /api/bookings?travellerId={id}` | ❌ À implémenter |
| `logging_service.py` | POST vers endpoint feedback (à confirmer) | ❌ À implémenter |

---

## Performance — Réduction Temps de Réponse

### Problème identifié
`hotel_node` fetchait 1203 hôtels via pagination (12 requêtes HTTP, `take=100`).
Même avec cache fichier JSON, la désérialisation d'un fichier 5MB+ restait lente.

### Solution critique validée (2026-06-02)

**1. `take=500` au lieu de `take=100`**
→ 3 requêtes HTTP au lieu de 12 pour paginer le catalogue complet.

**2. Architecture Tier 1 / Tier 2**
→ `GET /api/hotel-services` embarque les données hôtel complètes dans chaque entrée.
→ Tier 1 : **1 seul appel API** pour obtenir les ~15 hôtels partenaires + leurs services.
→ Tier 2 : catalogue complet (1203 hôtels) activé **uniquement si Tier 1 < 2 résultats**.
→ Cas courant (partenaires) : **< 50ms** après premier chargement en cache.

**3. Cache centralisé avec persistance fichier**
→ Premier appel : fetch API → stocké en mémoire + fichier JSON.
→ Appels suivants (dans TTL) : retour mémoire instantané.

> **Règle à ne pas casser** : tout nouveau service de recommandation doit suivre
> ce pattern Tier 1 / Tier 2. Ne jamais fetcher un catalogue complet sans cache.

---

## Cache Strategy

Cache centralisé dans `app/services/cache_service.py` — instance globale `cache`.
Persistance JSON dans `app/.cache/zenifytrip_cache.json` — survit aux redémarrages.

```python
from app.services.cache_service import cache, SimpleTTLCache

# Lire
data = cache.get("hotels")

# Écrire
cache.set("hotels", data, SimpleTTLCache.TTL_HOTELS)

# Pattern get-or-set
data = cache.get_or_set("zones", ZoneService.get_zones, SimpleTTLCache.TTL_ZONES)
```

### Stratégie Tier 1 / Tier 2 (hotel_node)

`hotel_node` fonctionne en 2 niveaux :
- **Tier 1 (partenaires)** : 1 seul appel `GET /api/hotel-services` — hôtel embarqué dans la réponse. TTL 2h. ~10-15 hôtels uniques.
- **Tier 2 (catalogue)** : activé uniquement si Tier 1 retourne < 2 résultats après filtrage. `GET /api/hotels` paginé, TTL 24h.

> ⚠️ Les hôtels partenaires couvrent principalement Sousse/El Kantaoui et Djerba.
> Si la destination est Hammamet, Tunis, Monastir → Tier 2 sera systématiquement activé.

Chaque candidat inclut `"tier": "partner" | "catalogue"` pour que le Ranking Agent connaisse la priorité commerciale.

### TTL par domaine

| Clé cache | TTL | Constante |
|-----------|-----|-----------|
| `hotels` | 24h | `TTL_HOTELS` |
| `hotel_services` | 24h | `TTL_HOTELS` |
| `zones` | 24h | `TTL_ZONES` |
| `weather` | 2h | `TTL_WEATHER` |
| `maps` | 12h | `TTL_MAPS` |
| `activities` | 24h | `TTL_ACTIVITIES` |
| `profile` | 1h | `TTL_PROFILE` |
| `flights` | 6h | `TTL_FLIGHTS` |
| `airlines` | 24h | `TTL_AIRLINES` |
| `airports` | 24h | `TTL_AIRPORTS` |

### Helpers disponibles

| Méthode | Usage |
|---------|-------|
| `cache.get(key)` | Lecture (None si expiré) |
| `cache.set(key, value, ttl)` | Écriture + persist fichier |
| `cache.delete(key)` | Suppression |
| `cache.get_or_set(key, loader, ttl)` | Pattern fetch-if-miss |
| `cache.invalidate_prefix("flights_")` | Invalider un domaine entier |
| `cache.clear_expired()` | Purger les entrées expirées |
| `cache.stats()` | Métriques debug |

---

## flight_flux — Flux complet Flight Recommender

> Flux validé et testé (6/6 PASS) — session 2026-06-06.
> Fichiers : `app/services/flight_service.py` + `app/data/tunisia_destinations.py`
> + `app/nodes/recommendation/domain/flight_node.py` + `app/schemas/flight_schema.py`

```
User : "je veux aller à Kairouan en juillet"
              │
              ▼
constraints = {destination: "kairouan", start_date: "2026-07-10"}
              │
              ▼
get_flight_candidates(constraints)
    │
    ├── _extract_travel_month("2026-07-10") → 7
    │
    ├── TIER 1 : profil voyageur (USER RÉEL)
    │   └── pas de vols Kairouan dans profil → []
    │
    ├── city_to_airports("kairouan")          ← tunisia_destinations.py
    │   └── [NBE(60km), MIR(65km), SUF(70km)]
    │
    ├── Pour NBE (60km) :
    │   ├── filter_flights(target_iata="NBE") → vols atterrissant à NBE
    │   └── _enrich_with_destination()        ← tunisia_destinations.py
    │       ├── destination_features("NBE")   → tags, vibe, traveler_types
    │       ├── get_seasonal_advice("NBE", 7) → recommended + raison
    │       └── get_recommendation_reason("NBE", 7) → phrase FR
    │       → transfer_needed=True, transfer_distance_km=60
    │
    ├── Pour MIR (65km) : même chose
    ├── Pour SUF (70km) : même chose
    │
    └── Tri par match_score → top 10 candidats enrichis
              │
              ▼
flight_candidates = [
  {
    "flight_number": "TU101", "landing_airport": "NBE",
    "user_destination": "kairouan",
    "transfer_needed": True, "transfer_distance_km": 60,
    "transfer_label": "Enfidha-Hammamet",
    "seasonal_advice": {"recommended": True, "reason": "Hammamet en juillet..."},
    "recommendation_reason": "Enfidha en juillet : mer idéale. À voir : Yasmine Hammamet.",
    "destination_features": {"tags": ["plage","resort",...], "traveler_types": [...]}
  },
  { "landing_airport": "MIR", "transfer_distance_km": 65, ... },
  { "landing_airport": "SUF", "transfer_distance_km": 70, ... },
]
              │
              ▼
ranking_node → score = 70% user_score + 30% business_score
  user_score  : tags matchent keywords, saison ok, profil traveler_type
  business_score : tier profile > catalogue, transfert agence dispo
              │
              ▼
final_response :
  "Pour Kairouan, vol vers Enfidha (60km).
   Kairouan est idéale au printemps — juillet est chaud.
   Transfert agence disponible / taxi ~45 min."
```

### Cas particuliers gérés

| Cas | Comportement |
|-----|-------------|
| Destination avec aéroport (`"tunis"`) | `city_to_airports` → `[TUN(8km)]` → `transfer_needed=False` |
| Destination sans aéroport (`"kairouan"`) | → `[NBE, MIR, SUF]` → `transfer_needed=True` |
| Pas de destination (exploratory) | Chemin séparé → tous les vols sans filtre destination |
| Ville inconnue | Fallback texte brut sur l'API |
| USER RÉEL avec profil | Tier 1 enrichi aussi avec destination_features |

### Fonctions tunisia_destinations utilisées dans flight_service

| Fonction | Rôle |
|----------|------|
| `city_to_airports(city)` | Résout ville → liste aéroports avec distances |
| `destination_features(iata)` | Features brutes pour ranking (tags, vibe, saisons) |
| `get_seasonal_advice(iata, month)` | Conseil saisonnier — utilise travel_month fourni |
| `get_recommendation_reason(iata, month)` | Phrase FR prête pour final_response |

---

## Bugs Connus / TODO (par priorité)
1. **`llm_service.py` crash à l'import** — `"Bearer " + os.getenv("OLLAMA_API_KEY")` plante si `OLLAMA_API_KEY` est `None`
2. **`.env` syntaxe bash** — les lignes `export OLLAMA_API_KEY=...` et `export OLLAMA_BASE_URL=...` utilisent la syntaxe bash, ignorée par python-dotenv
3. **ProfileService async** — `get_traveller_profile` est `async` mais appelée de façon synchrone dans ProfileLoaderNode — retourne une coroutine, pas les données
4. **`OLLAMA_BASE_URL` incorrecte** — défaut `"https://ollama.com"` au lieu d'un vrai endpoint API
5. **`context_merger_node.py` mutation d'état** — mute l'état en place et retourne l'état entier ; devrait retourner uniquement `{"merged_context": merged}`
6. **`main.py` clé incorrecte** — `result.get("constraints", {})` mais les contraintes sont dans `result["intent_result"]["constraints"]`
7. **Routage conditionnel désactivé** — `clarification_checker` va toujours vers `final_response` ; les appels `add_conditional_edges` sont commentés dans `builder.py`
8. **Nodes de recommandation vides** — `hotel_node.py`, `flight_node.py`, `restaurant_node.py`, `activity_node.py`, `orchestrator_node.py` non implémentés
