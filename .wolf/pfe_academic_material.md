# Matière Première — Rapport PFE ZenifyTrip
> Extrait depuis CLAUDE.md + historique de sessions. Rédigé pour servir de source directe dans le rapport académique.
> Mis à jour : 2026-07-29

---

## 1. DÉCISIONS ARCHITECTURALES

### DA-01 — Module restaurant : Approche A (Google Places) vs B (LLM) vs C (Hybride)

**Décision** : Approche A retenue — Google Places API en Python pur, sans LLM dans le chemin de collecte.

**Alternatives écartées** :
- **Approche B — LLM seul (Groq llama-3.3-70b)** : le modèle invente des restaurants inexistants ou place des restaurants réels dans la mauvaise ville. Taux d'hallucination mesuré : **46 %** (6 restaurants vérifiés sur 12 → 3 réels et corrects, 3 partiellement réels, 6 inventés ou mal localisés). Exemples documentés : « Le Grand Vefour » (restaurant parisien placé à Tunis), « La Djerbienne » (restaurant réel de Tunis placé à Djerba). Éliminatoire pour un usage professionnel.
- **Approche C — Tavily Search + LLM** : coordonnées GPS absentes (0 %), latence élevée (7 607 ms en moyenne), coût estimé à 0,00777 USD par appel, fragile aux quotas Tavily. Données partielles insuffisantes pour le scoring haversine.

**Justification retenue** :
> « Approche A = données réelles fiables mais sans `recommendation_reason`. Approche B = hallucine 46 % du temps, inutilisable seule. Approche C = Google Places (données réelles) + LLM léger (enrichissement `recommendation_reason` uniquement sur données déjà vérifiées) → zéro hallucination + richesse sémantique. »

La génération de `recommendation_reason` est déléguée au `ranking_node` LLM déjà dans le pipeline — aucun LLM supplémentaire requis.

**Résultats mesurés (benchmark 2026-06-07, 6 scénarios)** :

| Approche | Candidats/session | Latence moy. | Coût/appel | GPS 100 % | Hallucination |
|----------|-------------------|--------------|------------|-----------|---------------|
| A — Google Places | 9,7 | 1 361 ms | 0,00 USD | ✅ | 0 % |
| B — LLM seul | 2,3 | 4 397 ms | 0,00428 USD | ❌ 0 % | **46 %** |
| C — Tavily+LLM | 4,3 | 7 607 ms | 0,00777 USD | ❌ 0 % | ~0 % |

---

### DA-02 — Semantic Node : modèle 8B → modèle 17B MoE

**Décision** : Migration de `llama-3.1-8b-instant` vers `llama-4-scout-17b-16e-instruct` (architecture MoE, 17B paramètres, 16 experts) pour le `semantic_node`.

**Alternative écartée** : `llama-3.1-8b-instant` — modèle trop léger pour le prompt de 300 lignes du `semantic_node`. Symptôme observé : le modèle 8B génère du code Python exécutable (`def process_intent(merged_context, weather_context):...`) au lieu de l'objet JSON attendu. Cause : incapacité à distinguer les instructions *décrivant* une logique (à exécuter mentalement) des instructions *demandant* du code.

**Justification retenue** : Architecture MoE : qualité proche d'un 70B dense sur les tâches de génération structurée, mais avec une limite TPM de 30 000 (5× supérieure au 70B). Adapté aux nodes avec des prompts longs (> 2 000 tokens).

**Résultats mesurés** : 0 erreur `Semantic LLM error` après migration. Score de test : 26/28 assertions PASS (les 2 restantes correspondent au scénario 8 / erreur 401 API indépendante du modèle).

---

### DA-03 — Activity Node : enrichissement sémantique rule-based vs LLM

**Décision** : Enrichissement des champs `best_season`, `audience`, `budget_level`, `indoor`, `duration_hours`, `nearby` par règles Python déterministes (0 appel LLM).

**Alternatives écartées** :
- `meta-llama/llama-4-scout-17b-16e-instruct` (Groq) → HTTP 404, modèle indisponible au moment de l'exécution.
- `llama-3.3-70b-versatile` (Groq) → Rate limit 429 dès le 60e document traité.
- Ollama Cloud → Accès suspendu (facturation).
- Sous-agents Claude → Limite de session après ~60 documents.

**Justification retenue** : Les champs `best_season`, `audience`, `budget_level`, `indoor` sont des classifications structurées à vocabulaire contrôlé, dont les règles sont explicites et universelles pour la Tunisie. Un document contenant le mot « plage » a nécessairement `best_season` incluant l'été. Ces règles sont déterministes par nature — elles ne nécessitent pas l'inférence probabiliste d'un LLM.

**Résultats mesurés** :
- Temps d'exécution : 30 secondes pour 1 928 documents via `bulk_write` par lots de 500.
- Couverture : 100 % des 2 345 documents ont tous les champs enrichis.
- Coût : 0 token, 0 appel API.

---

### DA-04 — Atlas Search dual-analyzer vs regex vs dictionnaire statique (matching cross-langue EN→FR)

**Décision** : MongoDB Atlas Search avec dual-analyzer (`lucene.french` + `lucene.english` via syntaxe `multi`) pour le matching entre keywords camelCase anglais produits par `semantic_node` et tags français stockés dans `activities_collection`.

**Alternatives écartées** :
- **Dictionnaire statique `_CAMELCASE_TO_FR`** (KEYWORD_MAP) : rejeté explicitement — « statique, fragile, maintenance infinie ❌ ». Chaque nouveau keyword du LLM nécessiterait une mise à jour manuelle du dictionnaire.
- **Filtre `$in` exact sur tags** : retournait 0 match pour tous les keywords camelCase anglais — aucun croisement entre vocabulaire EN (`culturalActivity`, `outdoor_activity`) et tags FR (`culture`, `plein-air`).
- **`dynamic: true` Atlas Search** : fonctionne mais utilise le standard analyzer sans stemming → `cultural` ≠ `culture` (distance d'édition = 2 > seuil fuzzy:1).
- **Syntax array `[{type,analyzer},{type,analyzer}]`** : index en statut `FAILED` sans message d'erreur sur MongoDB Atlas M0.

**Justification retenue** : La syntaxe `multi` objet crée un sous-analyseur nommé accessible comme `tags.en` dans les requêtes. Le mécanisme de matching repose sur la convergence de stems : `culture` (tag FR) → analyseur French → stem `cultur` ; `cultural` (extrait de `culturalActivity` après split camelCase) → analyseur English → stem `cultur` → MATCH cross-langue. La distance d'édition couvre également les paires proches : `adventure` ↔ `aventure` (distance = 1, fuzzy:1 → MATCH).

**Résultats mesurés (3/3 PASS, 2026-07-29)** :

| Test | Keywords | Destination | Résultats Atlas | Résultats $in |
|------|----------|-------------|-----------------|---------------|
| A | `['culturalActivity','heritage']` | monastir | 5 docs, score top = 1,973 | 0 ❌ |
| B | `['beach','outdoor_activity']` | djerba | 5 docs, score top = 2,590 | 0 ❌ |
| C | `['culturalActivity']` | monastir | 5 docs | 0 ❌ |

---

### DA-05 — Cache profil voyageur : Redis → MongoDB Atlas

**Décision** : Migration du cache profil (`ProfileCacheService`) de Redis vers une collection MongoDB dédiée (`traveller_profile_cache`) avec index TTL natif.

**Alternative écartée** : Redis — seul et unique consommateur réel de Redis dans le codebase (`profile:{traveller_id}`). Représentait un point de défaillance optionnel supplémentaire : `redis_config.py::r` peut être `None` si mal configuré, désactivant silencieusement le cache sans erreur visible.

**Justification retenue** :
1. MongoDB Atlas est déjà une dépendance dure du projet (2 collections en production) — Redis était une dépendance supplémentaire pour un seul cas d'usage.
2. Un TTL pouvant atteindre 30 jours ressemble davantage à un enregistrement persistant avec expiration qu'à un cache mémoire volatil au sens Redis.
3. L'index TTL natif de MongoDB (`expireAfterSeconds=0` sur le champ `expires_at`) est fonctionnellement équivalent au `SETEX` Redis.
4. Interface publique de `ProfileCacheService` **inchangée** → zéro modification dans `load_profile_node.py`.

**Bug découvert pendant la migration** : `ttl()` retournait toujours `-2` silencieusement. Cause : `datetime.now(timezone.utc)` (aware) comparé à un datetime naïf retourné par pymongo par défaut. Fix : `datetime.utcnow()` dans toute la classe.

---

### DA-06 — Scoring candidats : additif V1 → multiplicatif V2

**Décision** : Passage du scoring additif `0,70 × user_score + 0,30 × business_score` à la formule multiplicative :
```
ranked_score = user_score × business_boost × availability_factor
business_boost = (1 + 0.30 × business_score) / 1.30
```

**Alternative écartée** : Modèle additif V1 — permettait à un `business_score` élevé de compenser un `user_score` faible. Un candidat hors sujet pour l'utilisateur (user_score = 0) mais commercialement prioritaire (business_score = 1) obtenait un score de 0,30, le faisant remonter dans le classement au détriment de candidats pertinents.

**Justification retenue** : Le modèle multiplicatif garantit que `user_score = 0 → ranked_score = 0`, quelle que soit la valeur de `business_score`. Le boost commercial amplifie uniquement les candidats déjà pertinents — il ne sauve jamais un candidat hors sujet. Formulation : « le business BOOSTE les candidats pertinents, ne sauve JAMAIS un candidat hors sujet ».

---

### DA-07 — Pipeline informatif séparé du pipeline recommandation

**Décision** : Les intents `travel_question` et `booking_question` empruntent un chemin dédié (`clarification_checker → information_node → final_response`) au lieu de traverser le pipeline complet (weather → semantic → orchestrator → domaines → ranking).

**Alternative écartée** : Router ces intents vers le pipeline recommandation complet — inutile et coûteux pour des questions factuelles qui n'ont pas de candidats à scorer.

**Justification retenue** : Séparation des responsabilités. Un `information_node` rule-based (5 sous-types : `follow_up_place`, `weather`, `booking_info`, `session_planning`, `factual`) résout la plupart des questions conversationnelles en < 1 ms sans appel LLM. Seul `final_response_node` (Agent 1) est appelé pour formuler la réponse.

---

### DA-08 — LLM provider : Groq → Gemini avec fallback automatique

**Décision** : Migration de Groq vers Gemini 2.0 Flash (Google AI Studio) comme provider principal, avec fallback automatique Gemini → Groq sur erreur 429.

**Alternative écartée** : Groq seul — quota TPD de 100 000 tokens/jour (tier gratuit) insuffisant dès le développement actif (épuisé plusieurs fois dans la même session de tests).

**Justification retenue** : Gemini (Google AI Studio, tier gratuit) offre 1 500 requêtes/jour sans expiration. Le fallback automatique dans `call_llm()` permet aux deux quotas de se compléter au lieu de constituer chacun un point de défaillance unique.

**Limite observée** : Gemini possède une limite par minute assez basse en tier gratuit — observée après une poignée d'appels rapprochés, résolue en quelques dizaines de secondes.

---

### DA-09 — Matching géographique : substring → word-boundary regex

**Décision** : Remplacement du matching par sous-chaîne simple (`norm_key in normalized_text`) par un matching par **limites de mot** (`\b` regex) dans `_match_city_in_text`.

**Cause du bug** : `"tunis"` matchait dans `"tunisie"` (faux positif) → la destination « Tunisie » était résolue comme la ville « Tunis », sautant la clarification géographique.

**Justification retenue** : Le matching par limites de mot ne peut que retirer des faux positifs, jamais en introduire. Testé sur tous les cas existants (133 villes) — zéro régression.

**Impact** : Un helper `is_country_level_destination()` complémentaire détecte les mentions de pays (`tunisie`, `tunisia`) pour déclencher la clarification au lieu de retomber sur le texte brut.

---

### DA-10 — Sources données activités : TripAdvisor + OSM + Wikivoyage

**Décision** : Combinaison TripAdvisor (scraping), OpenStreetMap (Overpass API) et Wikivoyage (API FR) pour construire `activities_collection`.

**Alternatives écartées** :
- **Google Maps API** : `REQUEST_DENIED` — facturation Google Cloud non activée sur le projet.
- **API officielle ONT Tunisie** : accessible uniquement via partenariats institutionnels hors périmètre académique.
- **TripAdvisor API officielle** : accès restreint aux partenaires commerciaux enregistrés.

**Justification retenue** : Données réelles, structurées, à coût nul, sans hallucination. TripAdvisor = couverture et popularité ; OSM = coordonnées GPS précises ; Wikivoyage = expériences locales authentiques absentes des annuaires touristiques classiques.

---

## 2. CHIFFRES ET MÉTRIQUES MESURÉS

### Pipeline
| Indicateur | Valeur | Source |
|------------|--------|--------|
| Nodes dans le graphe LangGraph | 19 | builder.py |
| Phases du pipeline | 5 | CLAUDE.md |
| Scénarios E2E validés (VERSION 6) | 8/8 PASS | test_e2e.py 2026-07-08 |
| Scénarios E2E validés (VERSION 5) | 3/3 PASS | test_activity_graph.py 2026-06-13 |
| Scénarios VERSION 1 validés | 7/7 PASS | 2026-05-24 |
| Latence squelette day planner (Redis chaud) | < 0,2 s | day_skeleton_node streaming |
| Latence squelette day planner (Redis froid) | ~2–3 s | day_skeleton_node streaming |
| Latence réponse complète | ~10 s | main.py streaming |

### Benchmark restaurant (2026-06-07)
| Métrique | Approche A | Approche B |
|----------|-----------|-----------|
| Candidats totaux (6 scénarios) | 56 | 15 |
| Latence moyenne appel froid | 1 467 ms | 1 493 ms |
| GPS présent | 100 % | 0 % |
| Hallucination vérifiée | 0 % | **46 %** |
| Coût total 6 appels | 0,00 USD | 0,005 USD |
| Tokens consommés | 0 | 8 843 |

### Collection `restaurant_collection`
| Indicateur | Valeur |
|------------|--------|
| Documents totaux | 26 575 |
| Villes / zones distinctes | 67 |
| Photo présente | 83,9 % |
| `establishment_types` renseigné | 100 % |
| GPS présent | 63,5 % |
| Horaires (`opening_hours_text`) | 99,9 % |
| Tags nettoyés (corrections rétroactives) | 778 documents, 838 occurrences retirées |

### Collection `activities_collection`
| Indicateur | Valeur |
|------------|--------|
| Documents totaux | 2 345 |
| GPS précis (lat + lng non null) | 99,9 % (2 342/2 345) |
| Description non nulle | 100 % |
| `best_season` renseigné | 100 % |
| `audience` renseigné | 100 % |
| `budget_level` renseigné | 100 % |
| `duration_hours` renseigné | 100 % |
| `indoor` renseigné | 100 % |
| `activity_type` renseigné | 100 % (dont 473 = « unknown », 20,2 %) |
| `is_bookable: True` | 15,8 % (370/2 345) |
| Destinations distinctes | 69 |
| Source TripAdvisor | 66,5 % (1 560 docs) |
| Source OSM | 20,6 % (484 docs) |
| Source Wikivoyage | 4,6 % (107 docs) |
| Activités authentiques locales | 107 docs |

### Scoring
| Constante | Valeur par défaut | Configurable via |
|-----------|------------------|-----------------|
| `USER_SCORE_WEIGHT` | 0,70 | `settings.py` + `.env` |
| `BUSINESS_SCORE_WEIGHT` | 0,30 | `settings.py` + `.env` |
| Tier partner → `business_score` | 0,85 | `ranking_node.py` |
| Tier agency/internal | 0,80 | `ranking_node.py` |
| Tier catalogue | 0,45 | `ranking_node.py` |
| Tier external/MongoDB | 0,20 | `ranking_node.py` |
| `availability_factor` dispo confirmée | 1,00 | formule V2 |
| `availability_factor` inconnu, agence forte (best user_score ≥ 0,60) | 0,60 | `settings.py` |
| `availability_factor` inconnu, agence faible | 0,90 | `settings.py` |

### Hôtels (API interne)
| Indicateur | Valeur |
|------------|--------|
| Hôtels dans le catalogue | 746 |
| Hôtels Tier 1 (partenaires) | ~15 |
| Requêtes HTTP avec `take=100` | 12 requêtes |
| Requêtes HTTP avec `take=500` | 3 requêtes |
| Latence Tier 1 (cache chaud) | < 50 ms |

### APIs internes (staging)
| Endpoint | Volume |
|----------|--------|
| `/api/hotels` | 746 hôtels |
| `/api/flights` | 272 vols |
| `/api/bookings` | 141 réservations |
| `/api/hotel-services` | 26 services |
| `/api/tourist-guides` | 19 guides |

### Atlas Search (2026-07-29)
| Indicateur | Valeur |
|------------|--------|
| Temps de build de l'index sur 2 345 docs | ~25 s |
| Match `$in` exact (keywords EN, tags FR) | 0 résultats |
| Match Atlas Search dual-analyzer | 5 résultats (test A monastir) |
| Score Atlas top résultat (test A) | 1,973 |
| Score Atlas top résultat (test B djerba) | 2,590 |

---

## 3. INNOVATIONS ET DIFFÉRENCIATEURS

### IN-01 — Scoring commercial explicite et configurable sans redéploiement

ZenifyTrip implémente un `business_score` explicite, documenté et **modifiable sans toucher au code** via les variables d'environnement `USER_SCORE_WEIGHT` et `BUSINESS_SCORE_WEIGHT` dans `.env`. Aucun acteur du benchmark (Expedia/Romie, Mindtrip, Kayak, TripAdvisor, Booking.com) ne documente publiquement une logique commerciale de ce niveau d'auditabilité. La formule V2 multiplicative garantit en outre qu'un candidat hors sujet pour l'utilisateur ne peut jamais être promu par le score commercial.

**Argument académique** : la plupart des systèmes de recommandation commerciaux intègrent un biais commercial implicite non documenté (position payée, partenariat non déclaré). ZenifyTrip rend ce biais explicite, mesurable et configurable — ce qui constitue une contribution à la transparence algorithmique.

---

### IN-02 — Booking-Aware Day Planner (ancres immuables)

Le `day_planner_node` planifie **autour** de ce que le voyageur a déjà payé, et non à côté. Les ancres `booking_anchors` (repas inclus, services bookés, heures de vol, transfert) sont déclarées immuables dans le prompt et dans la logique Python. Conséquences concrètes :
- All Inclusive → aucun restaurant payant en créneau repas.
- Petit-déjeuner inclus → jamais de café payant le matin.
- Spa booké 15h → le créneau 15h est verrouillé dans le squelette avant que le LLM génère quoi que ce soit.

Aucun système concurrent recensé ne documente ce niveau de cohérence entre le dossier de réservation et le planning généré.

---

### IN-03 — Squelette streamé en < 200 ms (Instant Skeleton)

Le `day_skeleton_node` génère un squelette de journée en Python pur (0 appel LLM, 0 API externe) en < 10 ms. Grâce au streaming LangGraph (`stream_mode="updates"`), l'utilisateur voit une structure de journée avec ancres posées et slots ouverts à l'écran en **0,2 s** (Redis chaud) ou **2–3 s** (Redis froid), pendant que les 10 secondes suivantes remplissent les détails. Ce pattern de streaming progressif réduit la perception de latence sans modifier la latence réelle.

---

### IN-04 — Mémoire de session implicite (rejets minés)

`utils/session_memory.py` mine la `conversation_history` courante pour extraire les rejets implicites (« non pas de plage », « trop loin ») par analyse de fenêtre glissante < 5 mots avec neutralisateurs (« pas mal » ne déclenche pas de rejet). Un candidat rejeté dans la session ne peut plus être reproposé, même si son `ranked_score` est supérieur à un candidat non rejeté. Cette logique est invisible pour l'utilisateur mais perceptible dans la qualité des suggestions successives.

---

### IN-05 — Pipeline double-chemin RECOMMENDATION / INFORMATIVE

ZenifyTrip sépare structurellement deux types de requêtes qui, dans d'autres systèmes, seraient gérées par le même agent :
- **Pipeline recommandation** (weather → semantic → orchestrator → domaines → ranking → day_planner) : 10–15 s, 8+ appels LLM/API.
- **Pipeline informatif** (information_node rule-based → final_response) : < 1 s, 1 seul appel LLM.

Cette bifurcation permet de répondre à « quelle est la météo à Sousse ? » ou « qu'est-ce que j'ai réservé demain ? » en < 1 seconde sans mobiliser le pipeline de recommandation complet.

---

### IN-06 — Dégradation gracieuse si Redis down

`redis_config.py::r` peut être `None` si Redis est indisponible. Le système continue de fonctionner en mode dégradé : cache profil absent (appel API à chaque requête), mémoire cross-session absente (session stateless), mais aucun crash. Cette propriété est garantie par la conception — chaque composant qui lit Redis vérifie `if r is None` avant tout appel.

---

### IN-07 — Matching cross-langue sans dictionnaire statique

La combinaison `_normalize_keywords()` (split camelCase côté Python) + index Atlas Search dual-analyzer (`lucene.french` + `lucene.english`) permet de faire correspondre des keywords anglais produits par le LLM (`culturalActivity`) avec des tags français stockés en base (`culture`) via convergence de stems, sans maintenance d'un dictionnaire de traduction. Approche généralisable à tout nouveau keyword sans modification du code.

---

### IN-08 — Disponibilité tri-state (None ≠ False)

Le contrat d'`is_available` dans tous les schémas de candidats distingue explicitement trois états : `True` (confirmé disponible), `False` (confirmé indisponible), `None` (inconnu — source non vérificatrice). Cette distinction garantit qu'une source MongoDB qui ne vérifie pas la disponibilité en temps réel ne peut pas mentir en déclarant `True`. L'exclusion dure est réservée à `constraint_validator` (`is_available is False`) — les états `True` et `None` traversent le ranking sans être éliminés prématurément.

---

## 4. CHOIX TECHNOLOGIQUES JUSTIFIÉS

### CT-01 — LangGraph (vs LangChain Agents, CrewAI, AutoGen)

LangGraph offre un contrôle déterministe du flot d'exécution via un graphe orienté (`StateGraph`). Contrairement aux agents LangChain classiques (boucle ReAct non bornée), LangGraph garantit :
- Un chemin d'exécution prévisible et traçable (chaque arête est explicite dans `builder.py`).
- Un support natif du fan-out parallèle et du fan-in synchronisé.
- Un streaming par node (`stream_mode="updates"`) permettant le pattern Instant Skeleton.
- Une gestion d'état partagé via `GraphState` TypedDict — source unique de vérité pour tous les nodes.

**Contrainte découverte** : si deux nodes de profondeurs différentes convergent vers le même node, LangGraph exécute ce node une fois par chemin entrant (double exécution → `InvalidUpdateError`). Règle de conception dérivée de ce bug : toujours placer les nodes de convergence au **même niveau de profondeur**.

---

### CT-02 — Pydantic v2 pour les contrats inter-agents

Chaque échange entre nodes est typé par un schéma Pydantic v2. Les `field_validator` normalisent les valeurs invalides au lieu de lever des exceptions — garantissant la robustesse du pipeline face aux sorties imprécises des LLMs. Exemple : `confidence` est clampée entre 0 et 1 même si le LLM retourne `"0.95"` (string) ou `1.2` (hors borne).

---

### CT-03 — MongoDB Atlas Search (vs Elasticsearch, pgvector)

MongoDB Atlas Search est disponible gratuitement sur le cluster M0 déjà utilisé par le projet. L'alternative Elasticsearch nécessiterait une infrastructure dédiée. pgvector (recherche vectorielle) est anticipé pour les évolutions futures (champ `embedding vector(384)` prévu dans le schéma des activités) mais prématuré sur un dataset de 2 345 documents où le pattern matching reste plus performant.

---

### CT-04 — Groq (free tier) + Gemini 2.0 Flash (free tier) comme stack LLM

Choix guidé par la contrainte de coût nulle pour un projet de stage :
- **Groq** : inférence très rapide, modèles Llama 3 disponibles gratuitement (100 000 tokens/jour). Limite : TPD insuffisant en développement intensif.
- **Gemini 2.0 Flash** (Google AI Studio) : 1 500 requêtes/jour, gratuit, sans expiration. Provider principal depuis 2026-07-28.
- **Fallback automatique** : `call_llm()` bascule sur Groq en cas de 429 Gemini, évitant toute interruption de service.

---

### CT-05 — cloudscraper (vs requests) pour RestaurantGuru

RestaurantGuru utilise la protection anti-bot Cloudflare. Une simple bibliothèque `requests` est bloquée immédiatement. `cloudscraper` simule une empreinte de navigateur réel et a permis un scraping stable sur des milliers de requêtes. Choix nécessaire, pas optionnel.

---

### CT-06 — Architecture Tier 1 / Tier 2 pour les hôtels

`hotel_node` interroge d'abord `GET /api/hotel-services` (Tier 1 : ~15 hôtels partenaires, 1 seul appel API, données hôtel embarquées dans la réponse). Le Tier 2 (catalogue complet, 746 hôtels, 3 requêtes avec `take=500`) n'est activé que si Tier 1 retourne moins de 2 résultats après filtrage.

**Impact mesuré** : cas courant (partenaires) → < 50 ms après premier chargement en cache. Sans ce pattern, 12 requêtes HTTP à `take=100` pour paginer 746 hôtels.

---

## 5. PIPELINE DE PRÉPARATION DES DONNÉES

### 5.1 `restaurant_collection` (26 575 documents)

#### Sources
| Source | Rôle | Justification |
|--------|------|---------------|
| RestaurantGuru (scraping) | Principale — données structurées via JSON-LD schema.org | Couverture Tunisie, coût nul, données vérifiées |
| SerpApi (moteur `google_maps`) | Complémentaire — zones sans page RestaurantGuru dédiée + géocodage | Même qualité que Google Places sans facturation |
| ~~Google Maps API~~ | Tenté, abandonné | `REQUEST_DENIED` — facturation non activée |

**Note** : tout le scraping est programmatique (requêtes HTTP directes), sans navigateur automatisé. Cela garantit reproductibilité, scalabilité (67 villes × 13 types) et rejouabilité via checkpoint.

#### Étapes de préparation
1. **Scraping initial** (`fetch_restaurant_from_guru.py`) — 0 erreur, base fiable.
2. **Extension** (`add_establishment_types.py`) — typage `establishment_types` (100 % de couverture), découverte nouvelles villes, checkpoint par ville ajouté.
3. **Audit exhaustif** — taux de remplissage mesurés champ par champ.
4. **Correction tags corrompus** — `"dine inMeal type"` : métadonnées auto-générées par RestaurantGuru concaténées dans le HTML source. Fix dans les scrapers + nettoyage rétroactif : 778 documents, 838 occurrences.
5. **Correction bug `business_score`** — lecture prioritaire de `doc.get("business_score")` au lieu d'une constante uniforme.
6. **Audit couverture géographique** — 13 zones touristiques sans page RestaurantGuru identifiées (Sidi Bou Said, Port El Kantaoui, Skanes, Aghir, etc.).
7. **Enrichissement SerpApi** — > 1 100 nouveaux établissements pour les zones sous-couvertes.
8. **Enrichissement catégories** (`categories`) — passe LLM (Groq) puis auto-classification, taux porté de 13,1 % à > 18 %.

#### Champs-clés
| Champ | Couverture | Rôle |
|-------|-----------|------|
| `name` + `city` | 100 % | Clé de déduplication (index unique) |
| `establishment_types` | 100 % | Filtre créneau horaire (matin/midi/soir) |
| `photo_url` | 83,9 % | Affichage |
| `opening_hours_text` | 99,9 % | Affichage |
| `geo.lat` / `geo.lng` | 63,5 % | Calcul haversine |
| `rating` | 27 % | Signal qualité dans le scoring |

---

### 5.2 `activities_collection` (2 345 documents)

#### Sources
| Source | Docs | % | Rôle |
|--------|------|---|------|
| TripAdvisor (scraping) | 1 560 | 66,5 % | Attractions populaires |
| OpenStreetMap (Overpass API) | 484 | 20,6 % | GPS précis |
| Wikivoyage FR API | 107 | 4,6 % | Expériences locales authentiques |
| GetYourGuide + agrégateurs | 194 | 8,3 % | Activités bookables |

#### Pipeline de 7 phases
| Phase | Opération | Résultat |
|-------|-----------|----------|
| 1 | Nettoyage + normalisation (rapidfuzz ≥ 90 %, mapping `activity_type`) | ~120 doublons supprimés |
| 2 | Enrichissement GPS (Nominatim L1→L2→L3, centroïde en fallback) | 99,9 % GPS précis |
| 3 | Descriptions LLM (Claude claude-sonnet-4-6, 24 batches parallèles) | 100 % descriptions non nulles |
| 4 | Scraping expériences complémentaires (GetYourGuide + playwright) | +106 docs bookables |
| A | Activités authentiques Wikivoyage (API FR, analyse Claude par sections « Faire ») | +97 docs (2 passes) |
| 6 | Sites UNESCO (10 fiches rédigées manuellement, 0 token LLM) | +10 docs haute qualité |
| 5 | Enrichissement sémantique rule-based (0 LLM, 30 s, 1 928 docs) | 100 % tous champs contextuels |

#### Couverture géographique (69 destinations)
Top 5 par volume : Tunis (396) · Sousse (187) · Djerba (124) · Monastir (120) · Tozeur (116)

#### Tests de recommandation réels (2026-07-27)
| Requête | Résultat | Verdict |
|---------|----------|---------|
| Activités après-midi Monastir | 120 docs | ✅ |
| Famille Djerba en été | 48 docs | ✅ |
| Expérience authentique Kairouan | 65 docs | ✅ |
| Day-trip depuis Sousse, ≤ 4h | 254 docs | ✅ |
| Intérieur Tunis (il pleut) | 97 docs | ✅ |
| Gratuit à Sfax | 3 docs | ⚠️ limité |

---

## 6. LIMITES ET PERSPECTIVES

### 6.1 Limites actuelles (honnêteté académique)

| Limite | Impact | Raison |
|--------|--------|--------|
| 20,2 % des activités ont `activity_type = "unknown"` | Scoring moins précis sur ces docs | Catégories TripAdvisor non mappables vers les 5 types du schéma |
| Champ `categories` des restaurants trop bruité (~24 valeurs parasites) | Non utilisable comme filtre fiable | Noms de circuits complets et comptes entre parenthèses issus du scraping |
| 3 activités gratuites à Sfax | Couverture insuffisante pour la 3e ville de Tunisie | Ville secondaire peu représentée sur TripAdvisor |
| `is_bookable: True` = 15,8 % des activités | Faible potentiel de revenu direct via ce canal | Majorité des activités ne sont pas commercialisées via l'agence |
| `price_level` restaurants : 32,5 % de couverture | Filtrage budget partiel | Signal textuel trop rare pour une inférence fiable (0,17 % via extraction texte) |
| `get /api/activities` HTTP 500 | Fallback MongoDB obligatoire | Bug DB côté backend staging non corrigé |
| Quota LLM (Groq 100K/jour, Gemini ~limite/min) | Throughput limité pour 100 utilisateurs simultanés | Contrainte tier gratuit |
| Phase 5 mémoire cross-session Redis | Non opérationnel en production | Point d'injection (`session_signals`) en place, écriture non implémentée |

### 6.2 Perspectives documentées

**1. Collaborative Filtering**
Le CF nécessite un volume minimum de plusieurs centaines d'utilisateurs actifs avec historique. Infrastructure préparée : `UserInteraction`, logging des interactions, `cf_scorer.py` placeholder. À activer sur données réelles.

**2. Recherche vectorielle (embeddings)**
Modèle prévu : `paraphrase-multilingual-MiniLM-L12-v2` (384 dimensions, multilingue FR/AR/EN). Champ `embedding vector(384)` anticipé dans le schéma des activités. Prématuré sur le dataset actuel (pattern matching suffisant). Infrastructure Docker préparée.

**3. Cache distribué Redis (remplacement cache fichier JSON)**
`cache_service.py` est déjà abstrait et compatible Redis. La migration ne nécessite pas de modification d'interface.

**4. Quiz de clarification en-conversation**
Remplacement du dialogue texte par un pool d'options rule-based (villes de `tunisia_destinations.py`, intérêts des pools de `semantic_node`, filtré via `session_memory.py`). Résout plusieurs champs bloquants en un seul écran. Validé comme direction produit.

**5. Filtrage des données placeholder du catalogue vols staging**
Des vols de test avec aéroports fictifs (`IATA inexistant`), durée nulle et `scheduleStatus: "placeholder"` polluent les recommandations en environnement staging. Filtre à ajouter dans `flight_service.py`.

---

## 7. ARGUMENT MÉTHODOLOGIQUE RÉUTILISABLE

> « La revue de code seule n'aurait détecté aucun des 9 bugs de production identifiés en VERSION 7. Tous nécessitaient une exécution réelle du graphe LangGraph complet, avec de vraies données (vrai LLM, vraie MongoDB Atlas, vraies APIs externes), sur des requêtes formulées comme un vrai voyageur les écrirait. Ce résultat confirme que pour les systèmes multi-agents, le test d'intégration end-to-end sur données réelles est irremplaçable : les tests unitaires par node valident la cohérence interne mais masquent les interactions entre nodes, les comportements imprévus des LLMs sur des entrées réelles, et les dépendances d'infrastructure silencieuses. »

---

## 8. CONCURRENTS — ANGLES MORTS EXPLOITABLES

Source : étude concurrentielle automatisée (2026-07-03), 9 acteurs analysés.

**Couverture fiable** : Expedia/Romie (✅ vérifié), Mindtrip.ai (✅ vérifié).
**Angles morts documentés** : Booking.com, Google Travel/Gemini, Layla AI, Wonderplan, Hopper — zéro source exploitable sur l'architecture IA interne.

| Angle mort constaté | Différenciateur ZenifyTrip |
|--------------------|---------------------------|
| Aucun acteur ne documente une architecture multi-agents superviseur/spécialisés | Pipeline LangGraph documenté, 19 nodes traçables |
| Aucune mention de logique commerciale explicite (offres internes vs externes) | `business_score` explicite, configurable sans redéploiement |
| Personnalisation = « mémoire » marketing, rarement scoring dynamique | Score ajustable live en session (session_memory) |
| Aucune détection d'intention implicite/émotionnelle documentée | Angle mort chez tous les 9 acteurs — différenciateur potentiel |
| Latence non traitée comme sujet produit | Instant Skeleton < 200 ms (streaming LangGraph) |
| Anti-hallucination : « on utilise nos propres données » (opaque) | `constraint_validator` rule-based : règles vérifiables |
| Aucun acteur ne confirme utiliser LangGraph, LangChain, CrewAI ou AutoGen | — (opacité du marché documentée) |
