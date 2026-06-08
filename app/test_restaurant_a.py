import sys
import io
import time
import json

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from app.nodes.recommendation.domain.restaurant_node_a import RestaurantNodeA
from app.services.restaurant_service_a import RestaurantServiceA
from app.services.cache_service import cache

# ─────────────────────────────────────────────────────────────────────────────
# Champs obligatoires dans chaque candidat
# ─────────────────────────────────────────────────────────────────────────────

REQUIRED_FIELDS = [
    "id", "name", "rating", "match_score",
    "matched_criteria", "tier", "source",
]

VALID_TIERS = {"nearby", "text_search"}

# ─────────────────────────────────────────────────────────────────────────────
# Profil simulé USER RÉEL — hôtel avec ID connu
# ─────────────────────────────────────────────────────────────────────────────

PROFILE_REAL_SOUSSE = {
    "traveller_profile": {
        "first_name": "Ahmed", "last_name": "Ben Ali",
        "has_partner": True, "child_count": 0, "baby_count": 0,
        "traveler_type": "couple",
    },
    "availability": {
        "departure_date": "2026-07-01",
        "return_date": "2026-07-08",
        "duration_days": 7,
    },
    "route": {"origin": "Paris", "destination": "Sousse"},
    "tags": {"tags": [], "travellerTags": []},
    "travel_preferences": {
        "hotel_id": "1",          # ID existant dans le catalogue API
        "hotel_name": "Hotel Sousse Palace",
        "hotel_stars": 4,
        "meal_plan": "half_board",
        "room_type": "Double",
        "nights": 7,
        "hotel_level": "luxury",
    },
}

PROFILE_REAL_FAMILLE = {
    "traveller_profile": {
        "first_name": "Sonia", "last_name": "Triki",
        "has_partner": True, "child_count": 2, "baby_count": 0,
        "traveler_type": "family",
    },
    "availability": {
        "departure_date": "2026-08-01",
        "return_date": "2026-08-10",
        "duration_days": 9,
    },
    "route": {"origin": "Tunis", "destination": "Djerba"},
    "tags": {"tags": [], "travellerTags": []},
    "travel_preferences": {
        "hotel_id": "2",          # ID existant dans le catalogue API
        "hotel_name": "Djerba Resort",
        "hotel_stars": 4,
        "meal_plan": "all_inclusive",
        "room_type": "Family",
        "nights": 9,
        "hotel_level": "luxury",
    },
}

# ─────────────────────────────────────────────────────────────────────────────
# Scénarios — 6 cas définis dans CLAUDE.md
# ─────────────────────────────────────────────────────────────────────────────

SCENARIOS = [
    {
        "name": "1 — USER RÉEL | Sousse | seafood medium budget",
        "expect_empty": False,
        "expect_tier": "nearby",
        "state": {
            "user_type":      "real",
            "suggestion_mode": "precise_plan",
            "semantic_query": "sousse seafood restaurant",
            "global_keywords": ["seafoodRestaurant", "localCuisine"],
            "contextual_keywords": ["sousse", "summer", "mediumBudget"],
            "merged_context": {
                "destination": "Sousse",
                "budget_level": "medium",
                "is_family": False,
                "restaurant_preferences": ["seafood"],
            },
            "profile_data": PROFILE_REAL_SOUSSE,
            "weather_context": {"insights": {"is_hot_day": True, "is_sunny_day": True}},
        },
    },
    {
        "name": "2 — USER RÉEL | Djerba | famille budget medium",
        "expect_empty": False,
        "expect_tier": "nearby",
        "state": {
            "user_type":      "real",
            "suggestion_mode": "precise_plan",
            "semantic_query": "djerba family restaurant local cuisine",
            "global_keywords": ["familyRestaurant", "localCuisine", "traditionalCuisine"],
            "contextual_keywords": ["djerba", "summer", "mediumBudget"],
            "merged_context": {
                "destination": "Djerba",
                "budget_level": "medium",
                "is_family": True,
                "restaurant_preferences": [],
            },
            "profile_data": PROFILE_REAL_FAMILLE,
            "weather_context": {},
        },
    },
    {
        "name": "3 — USER NATIF | Tunis | cuisine locale",
        "expect_empty": False,
        "expect_tier": "text_search",
        "state": {
            "user_type":      "native",
            "suggestion_mode": "precise_plan",
            "semantic_query": "tunis local tunisian restaurant street food",
            "global_keywords": ["localCuisine", "streetFood", "traditionalCuisine"],
            "contextual_keywords": ["tunis", "mediumBudget"],
            "merged_context": {
                "destination": "Tunis",
                "budget_level": "medium",
                "is_family": False,
                "restaurant_preferences": [],
            },
            "profile_data": {},
            "weather_context": {},
        },
    },
    {
        "name": "4 — USER NATIF | exploratory | pas de destination",
        "expect_empty": False,
        "expect_tier": "text_search",
        "state": {
            "user_type":      "native",
            "suggestion_mode": "exploratory",
            "semantic_query": "restaurant tunisie local cuisine",
            "global_keywords": ["localCuisine"],
            "contextual_keywords": ["budgetFriendly"],
            "merged_context": {
                "destination": None,
                "budget_level": "low",
                "is_family": False,
                "restaurant_preferences": [],
            },
            "profile_data": {},
            "weather_context": {},
        },
    },
    {
        "name": "5 — Destination inconnue | fallback gracieux",
        "expect_empty": False,
        "expect_tier": "text_search",
        "state": {
            "user_type":      "native",
            "suggestion_mode": "precise_plan",
            "semantic_query": "restaurant VilleInexistante",
            "global_keywords": ["localCuisine"],
            "contextual_keywords": [],
            "merged_context": {
                "destination": "VilleInexistante",
                "budget_level": "medium",
                "is_family": False,
                "restaurant_preferences": [],
            },
            "profile_data": {},
            "weather_context": {},
        },
    },
    {
        "name": "6 — USER NATIF | Monastir | luxury romantique",
        "expect_empty": False,
        "expect_tier": "text_search",
        "state": {
            "user_type":      "native",
            "suggestion_mode": "precise_plan",
            "semantic_query": "monastir romantic restaurant sea view",
            "global_keywords": ["romanticDining", "fineRestaurant", "rooftopDining"],
            "contextual_keywords": ["monastir", "luxuryBudget", "summer"],
            "merged_context": {
                "destination": "Monastir",
                "budget_level": "luxury",
                "is_family": False,
                "restaurant_preferences": ["romantic", "vue mer"],
            },
            "profile_data": {},
            "weather_context": {},
        },
    },
]

# ─────────────────────────────────────────────────────────────────────────────
# BenchmarkTracker
# ─────────────────────────────────────────────────────────────────────────────

class BenchmarkTracker:

    def __init__(self, scenario_name: str):
        self.scenario_name    = scenario_name
        self.latency_total_ms = 0
        self.latency_api_ms   = 0
        self.latency_node_ms  = 0
        self.api_calls_google = 0
        self.cache_hits       = 0
        self.candidates_returned = 0
        self.avg_match_score  = 0.0
        self.pydantic_failures = 0
        self.search_mode      = "none"
        self.errors_caught    = 0

    def fill_from_service(self, benchmark: dict):
        self.api_calls_google = benchmark.get("api_calls_google", 0)
        self.cache_hits       = benchmark.get("cache_hits", 0)
        self.latency_api_ms   = benchmark.get("latency_api_ms", 0)
        self.search_mode      = benchmark.get("search_mode", "none")

    def fill_from_candidates(self, candidates: list):
        self.candidates_returned = len(candidates)
        if candidates:
            scores = [c.get("match_score", 0) for c in candidates]
            self.avg_match_score = round(sum(scores) / len(scores), 4)

    def report(self) -> dict:
        return {
            "scenario":            self.scenario_name,
            "approach":            "A — Python pur + Google Places",
            "latency_total_ms":    self.latency_total_ms,
            "latency_api_ms":      self.latency_api_ms,
            "latency_node_ms":     self.latency_node_ms,
            "api_calls_google":    self.api_calls_google,
            "cache_hits":          self.cache_hits,
            "candidates_returned": self.candidates_returned,
            "avg_match_score":     self.avg_match_score,
            "pydantic_failures":   self.pydantic_failures,
            "search_mode":         self.search_mode,
            "errors_caught":       self.errors_caught,
        }

# ─────────────────────────────────────────────────────────────────────────────
# Validation
# ─────────────────────────────────────────────────────────────────────────────

def validate(result: dict, scenario: dict) -> list:
    errors = []

    if "restaurant_candidates" not in result:
        errors.append("clé 'restaurant_candidates' manquante")
        return errors

    candidates = result["restaurant_candidates"]

    if not isinstance(candidates, list):
        errors.append(f"restaurant_candidates n'est pas une liste : {type(candidates)}")
        return errors

    if scenario["expect_empty"] and candidates:
        errors.append(f"résultat vide attendu mais {len(candidates)} candidats retournés")
        return errors

    if not candidates:
        return errors  # liste vide = fallback gracieux — OK

    # Tri décroissant par match_score
    scores = [c.get("match_score", 0) for c in candidates]
    if scores != sorted(scores, reverse=True):
        errors.append(f"candidats non triés par match_score : {scores}")

    for i, c in enumerate(candidates):
        pfx = f"candidat[{i}]"

        for field in REQUIRED_FIELDS:
            if field not in c:
                errors.append(f"{pfx} champ manquant : '{field}'")

        if not c.get("id"):
            errors.append(f"{pfx} 'id' vide")

        score = c.get("match_score")
        if score is None or not (0.0 <= score <= 1.0):
            errors.append(f"{pfx} match_score hors [0,1] : {score}")

        tier = c.get("tier")
        if tier not in VALID_TIERS:
            errors.append(f"{pfx} tier invalide : {tier!r}")

        if not isinstance(c.get("matched_criteria"), list):
            errors.append(f"{pfx} matched_criteria doit être une liste")

        rating = c.get("rating")
        if rating is not None and not (1.0 <= rating <= 5.0):
            errors.append(f"{pfx} rating hors [1,5] : {rating}")

        price = c.get("price_level")
        if price is not None and not (0 <= price <= 4):
            errors.append(f"{pfx} price_level hors [0,4] : {price}")

    return errors

# ─────────────────────────────────────────────────────────────────────────────
# Runner
# ─────────────────────────────────────────────────────────────────────────────

def run():
    node = RestaurantNodeA()
    total_pass = 0
    total_fail = 0
    all_reports = []

    for scenario in SCENARIOS:
        print(f"\n{'=' * 70}")
        print(f"SCENARIO {scenario['name']}")
        print("=" * 70)

        tracker = BenchmarkTracker(scenario["name"])
        state   = scenario["state"]

        # ── Invalidation cache avant chaque scénario (mesure à froid) ─
        cache.invalidate_prefix("rest_")

        # ── Appel service PREMIER — appel API réel, métriques correctes
        try:
            _, bench = RestaurantServiceA.get_restaurant_candidates(
                semantic_query=state.get("semantic_query") or "",
                global_keywords=state.get("global_keywords") or [],
                destination=(state.get("merged_context") or {}).get("destination"),
                budget_level=(state.get("merged_context") or {}).get("budget_level"),
                is_family=(state.get("merged_context") or {}).get("is_family", False),
                hotel_id=((state.get("profile_data") or {}).get("travel_preferences") or {}).get("hotel_id"),
                suggestion_mode=state.get("suggestion_mode") or "exploratory",
                max_candidates=10,
            )
            tracker.fill_from_service(bench)
        except Exception as e:
            tracker.errors_caught += 1

        # ── Appel node SECOND — cache chaud, mesure overhead node ─────
        t0     = time.time()
        result = node.run(state)
        tracker.latency_node_ms  = int((time.time() - t0) * 1000)
        tracker.latency_total_ms = tracker.latency_api_ms + tracker.latency_node_ms

        candidates = result.get("restaurant_candidates", [])
        tracker.fill_from_candidates(candidates)

        # ── Affichage candidats ───────────────────────────────────────
        print(f"  candidats  : {len(candidates)}")
        print(f"  mode       : {tracker.search_mode}")
        print(f"  latence    : api={tracker.latency_api_ms}ms | node={tracker.latency_node_ms}ms | total={tracker.latency_total_ms}ms")
        print(f"  API calls  : google={tracker.api_calls_google} | cache_hits={tracker.cache_hits}")

        for c in candidates[:5]:
            print(
                f"    [{c.get('tier','?'):12}] "
                f"{c.get('name','?')[:35]:<35} "
                f"⭐{c.get('rating') or '?'} "
                f"💰{c.get('price_level') if c.get('price_level') is not None else '?'} "
                f"score={c.get('match_score', 0):.3f} "
                f"dist={c.get('distance_km') or '-'}km"
            )
        if len(candidates) > 5:
            print(f"    ... (+{len(candidates) - 5} autres)")

        # ── Validation ────────────────────────────────────────────────
        errs = validate(result, scenario)

        if errs:
            total_fail += 1
            print(f"  [FAIL] {len(errs)} erreur(s) :")
            for e in errs:
                print(f"    - {e}")
        else:
            total_pass += 1
            print(f"  [PASS]")

        all_reports.append(tracker.report())

    # ── Rapport benchmark final ───────────────────────────────────────
    print(f"\n{'=' * 70}")
    print(f"RÉSULTATS : {total_pass} PASS / {total_fail} FAIL sur {len(SCENARIOS)} scénarios")
    print("=" * 70)

    print("\n── BENCHMARK COMPLET (JSON) ──")
    print(json.dumps(all_reports, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    run()
