import sys
import io
import time
import json
import logging

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
logging.basicConfig(level=logging.WARNING)  # silencer logs LLM pendant le test

from app.nodes.recommendation.domain.restaurant_node_b import RestaurantNodeB

# ─────────────────────────────────────────────────────────────────────────────
# Champs obligatoires
# ─────────────────────────────────────────────────────────────────────────────

REQUIRED_FIELDS = [
    "id", "name", "rating", "match_score",
    "matched_criteria", "tier", "source",
]

VALID_TIERS = {"llm_generated"}

# ─────────────────────────────────────────────────────────────────────────────
# Scénarios — identiques à test_restaurant_a.py pour comparaison directe
# ─────────────────────────────────────────────────────────────────────────────

SCENARIOS = [
    {
        "name": "1 — USER RÉEL | Sousse | seafood medium budget",
        "expect_empty": False,
        "state": {
            "user_type":       "real",
            "suggestion_mode": "precise_plan",
            "semantic_query":  "sousse seafood restaurant",
            "global_keywords": ["seafoodRestaurant", "localCuisine"],
            "contextual_keywords": ["sousse", "summer", "mediumBudget"],
            "merged_context": {
                "destination":  "Sousse",
                "budget_level": "medium",
                "is_family":    False,
                "restaurant_preferences": ["seafood"],
            },
            "profile_data": {},
            "weather_context": {},
        },
    },
    {
        "name": "2 — USER RÉEL | Djerba | famille budget medium",
        "expect_empty": False,
        "state": {
            "user_type":       "real",
            "suggestion_mode": "precise_plan",
            "semantic_query":  "djerba family restaurant local cuisine",
            "global_keywords": ["familyRestaurant", "localCuisine", "traditionalCuisine"],
            "contextual_keywords": ["djerba", "summer", "mediumBudget"],
            "merged_context": {
                "destination":  "Djerba",
                "budget_level": "medium",
                "is_family":    True,
                "restaurant_preferences": [],
            },
            "profile_data": {},
            "weather_context": {},
        },
    },
    {
        "name": "3 — USER NATIF | Tunis | cuisine locale",
        "expect_empty": False,
        "state": {
            "user_type":       "native",
            "suggestion_mode": "precise_plan",
            "semantic_query":  "tunis tunisian street food restaurant",
            "global_keywords": ["localCuisine", "streetFood", "traditionalCuisine"],
            "contextual_keywords": ["tunis", "mediumBudget"],
            "merged_context": {
                "destination":  "Tunis",
                "budget_level": "medium",
                "is_family":    False,
                "restaurant_preferences": [],
            },
            "profile_data": {},
            "weather_context": {},
        },
    },
    {
        "name": "4 — USER NATIF | exploratory | pas de destination",
        "expect_empty": False,
        "state": {
            "user_type":       "native",
            "suggestion_mode": "exploratory",
            "semantic_query":  "restaurant tunisie local cuisine",
            "global_keywords": ["localCuisine"],
            "contextual_keywords": ["budgetFriendly"],
            "merged_context": {
                "destination":  None,
                "budget_level": "low",
                "is_family":    False,
                "restaurant_preferences": [],
            },
            "profile_data": {},
            "weather_context": {},
        },
    },
    {
        "name": "5 — Destination inconnue | fallback gracieux",
        "expect_empty": True,
        "state": {
            "user_type":       "native",
            "suggestion_mode": "precise_plan",
            "semantic_query":  "restaurant VilleInexistante",
            "global_keywords": ["localCuisine"],
            "contextual_keywords": [],
            "merged_context": {
                "destination":  "VilleInexistante",
                "budget_level": "medium",
                "is_family":    False,
                "restaurant_preferences": [],
            },
            "profile_data": {},
            "weather_context": {},
        },
    },
    {
        "name": "6 — USER NATIF | Monastir | luxury romantique",
        "expect_empty": False,
        "state": {
            "user_type":       "native",
            "suggestion_mode": "precise_plan",
            "semantic_query":  "monastir romantic restaurant sea view",
            "global_keywords": ["romanticDining", "fineRestaurant", "rooftopDining"],
            "contextual_keywords": ["monastir", "luxuryBudget", "summer"],
            "merged_context": {
                "destination":  "Monastir",
                "budget_level": "luxury",
                "is_family":    False,
                "restaurant_preferences": ["romantic", "vue mer"],
            },
            "profile_data": {},
            "weather_context": {},
        },
    },
]

# ─────────────────────────────────────────────────────────────────────────────
# BenchmarkTracker — inclut les métriques LLM absentes dans Approche A
# ─────────────────────────────────────────────────────────────────────────────

class BenchmarkTracker:

    def __init__(self, scenario_name: str):
        self.scenario_name      = scenario_name
        self.latency_total_ms   = 0
        self.tokens_prompt      = 0
        self.tokens_completion  = 0
        self.tokens_total       = 0
        self.estimated_cost_usd = 0.0
        self.candidates_returned = 0
        self.avg_match_score    = 0.0
        self.pydantic_failures  = 0
        self.llm_calls          = 1
        self.cache_hit          = False
        self.errors_caught      = 0

    def compute_cost(self):
        # Groq llama-3.3-70b : ~$0.59 / 1M tokens input, $0.79 / 1M output
        input_cost  = (self.tokens_prompt     / 1_000_000) * 0.59
        output_cost = (self.tokens_completion / 1_000_000) * 0.79
        self.estimated_cost_usd = round(input_cost + output_cost, 6)

    def fill_from_candidates(self, candidates: list):
        self.candidates_returned = len(candidates)
        if candidates:
            scores = [c.get("match_score", 0) for c in candidates]
            self.avg_match_score = round(sum(scores) / len(scores), 4)

    def report(self) -> dict:
        return {
            "scenario":            self.scenario_name,
            "approach":            "B — LLM Groq llama-3.3-70b",
            "latency_total_ms":    self.latency_total_ms,
            "llm_calls":           self.llm_calls,
            "tokens_prompt":       self.tokens_prompt,
            "tokens_completion":   self.tokens_completion,
            "tokens_total":        self.tokens_total,
            "estimated_cost_usd":  self.estimated_cost_usd,
            "cache_hit":           self.cache_hit,
            "candidates_returned": self.candidates_returned,
            "avg_match_score":     self.avg_match_score,
            "pydantic_failures":   self.pydantic_failures,
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

    if scenario["expect_empty"]:
        if candidates:
            errors.append(f"résultat vide attendu (destination inconnue) — {len(candidates)} reçus")
        return errors

    if not candidates:
        return errors  # liste vide acceptable

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

        if not c.get("name"):
            errors.append(f"{pfx} 'name' vide")

        score = c.get("match_score")
        if score is None or not (0.0 <= score <= 1.0):
            errors.append(f"{pfx} match_score hors [0,1] : {score}")

        rating = c.get("rating")
        if rating is not None and not (1.0 <= rating <= 5.0):
            errors.append(f"{pfx} rating hors [1,5] : {rating}")

        tier = c.get("tier")
        if tier not in VALID_TIERS:
            errors.append(f"{pfx} tier invalide : {tier!r}")

        if not isinstance(c.get("matched_criteria"), list):
            errors.append(f"{pfx} matched_criteria doit être une liste")

    return errors

# ─────────────────────────────────────────────────────────────────────────────
# Runner
# ─────────────────────────────────────────────────────────────────────────────

def run():
    node        = RestaurantNodeB()
    total_pass  = 0
    total_fail  = 0
    all_reports = []
    total_tokens = 0

    for scenario in SCENARIOS:
        print(f"\n{'=' * 70}")
        print(f"SCENARIO {scenario['name']}")
        print("=" * 70)

        tracker = BenchmarkTracker(scenario["name"])
        state   = scenario["state"]

        # ── Appel node ────────────────────────────────────────────────
        t0     = time.time()
        result = node.run(state)
        tracker.latency_total_ms = int((time.time() - t0) * 1000)

        candidates = result.get("restaurant_candidates", [])
        tracker.fill_from_candidates(candidates)

        # ── Tokens depuis _last_tokens stocké dans le node ──────────
        # Cache LLM activé → 2ème run() retourne résultat caché + vrais tokens
        node.run(state)
        tracker.tokens_prompt     = node._last_tokens.get("prompt", 0)
        tracker.tokens_completion = node._last_tokens.get("completion", 0)
        tracker.tokens_total      = node._last_tokens.get("total", 0)
        tracker.compute_cost()
        total_tokens += tracker.tokens_total

        # ── Affichage ─────────────────────────────────────────────────
        print(f"  candidats  : {len(candidates)}")
        print(f"  latence    : {tracker.latency_total_ms}ms")
        print(f"  tokens     : prompt={tracker.tokens_prompt} | completion={tracker.tokens_completion} | total={tracker.tokens_total}")
        print(f"  coût est.  : ${tracker.estimated_cost_usd:.6f}")

        for c in candidates[:5]:
            reason = (c.get("recommendation_reason") or "")[:60]
            print(
                f"    [{c.get('tier','?'):13}] "
                f"{c.get('name','?')[:35]:<35} "
                f"⭐{c.get('rating') or '?'} "
                f"score={c.get('match_score', 0):.2f} "
                f"| {reason}"
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

    # ── Résumé ────────────────────────────────────────────────────────
    print(f"\n{'=' * 70}")
    print(f"RÉSULTATS : {total_pass} PASS / {total_fail} FAIL sur {len(SCENARIOS)} scénarios")
    print(f"TOKENS TOTAL session : {total_tokens}")
    print(f"COÛT ESTIMÉ session  : ${sum(r['estimated_cost_usd'] for r in all_reports):.6f}")
    print("=" * 70)

    print("\n── BENCHMARK COMPLET (JSON) ──")
    print(json.dumps(all_reports, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    run()
