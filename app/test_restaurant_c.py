import sys
import io
import time
import json
import logging

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
logging.disable(logging.CRITICAL)

from app.nodes.recommendation.domain.restaurant_node_c import RestaurantNodeC
from app.services.cache_service import cache

# ─────────────────────────────────────────────────────────────────────────────
REQUIRED_FIELDS = ["id", "name", "rating", "match_score", "matched_criteria", "tier", "source"]
VALID_TIERS     = {"tavily_llm"}

# ─────────────────────────────────────────────────────────────────────────────
# Scénarios — identiques à A et B
# ─────────────────────────────────────────────────────────────────────────────

SCENARIOS = [
    {
        "name": "1 — USER RÉEL | Sousse | seafood medium budget",
        "expect_empty": False,
        "state": {
            "user_type": "real", "suggestion_mode": "precise_plan",
            "semantic_query": "sousse seafood restaurant",
            "global_keywords": ["seafoodRestaurant", "localCuisine"],
            "contextual_keywords": ["sousse", "summer", "mediumBudget"],
            "merged_context": {"destination": "Sousse", "budget_level": "medium", "is_family": False},
            "profile_data": {}, "weather_context": {},
        },
    },
    {
        "name": "2 — USER RÉEL | Djerba | famille budget medium",
        "expect_empty": False,
        "state": {
            "user_type": "real", "suggestion_mode": "precise_plan",
            "semantic_query": "djerba family restaurant local cuisine",
            "global_keywords": ["familyRestaurant", "localCuisine", "traditionalCuisine"],
            "contextual_keywords": ["djerba", "summer", "mediumBudget"],
            "merged_context": {"destination": "Djerba", "budget_level": "medium", "is_family": True},
            "profile_data": {}, "weather_context": {},
        },
    },
    {
        "name": "3 — USER NATIF | Tunis | cuisine locale",
        "expect_empty": False,
        "state": {
            "user_type": "native", "suggestion_mode": "precise_plan",
            "semantic_query": "tunis tunisian street food restaurant",
            "global_keywords": ["localCuisine", "streetFood", "traditionalCuisine"],
            "contextual_keywords": ["tunis", "mediumBudget"],
            "merged_context": {"destination": "Tunis", "budget_level": "medium", "is_family": False},
            "profile_data": {}, "weather_context": {},
        },
    },
    {
        "name": "4 — USER NATIF | exploratory | pas de destination",
        "expect_empty": False,
        "state": {
            "user_type": "native", "suggestion_mode": "exploratory",
            "semantic_query": "restaurant tunisie local cuisine",
            "global_keywords": ["localCuisine"],
            "contextual_keywords": ["budgetFriendly"],
            "merged_context": {"destination": None, "budget_level": "low", "is_family": False},
            "profile_data": {}, "weather_context": {},
        },
    },
    {
        "name": "5 — Destination inconnue | fallback gracieux",
        "expect_empty": True,
        "state": {
            "user_type": "native", "suggestion_mode": "precise_plan",
            "semantic_query": "restaurant VilleInexistante",
            "global_keywords": ["localCuisine"],
            "contextual_keywords": [],
            "merged_context": {"destination": "VilleInexistante", "budget_level": "medium", "is_family": False},
            "profile_data": {}, "weather_context": {},
        },
    },
    {
        "name": "6 — USER NATIF | Monastir | luxury romantique",
        "expect_empty": False,
        "state": {
            "user_type": "native", "suggestion_mode": "precise_plan",
            "semantic_query": "monastir romantic restaurant sea view",
            "global_keywords": ["romanticDining", "fineRestaurant", "rooftopDining"],
            "contextual_keywords": ["monastir", "luxuryBudget", "summer"],
            "merged_context": {"destination": "Monastir", "budget_level": "luxury", "is_family": False},
            "profile_data": {}, "weather_context": {},
        },
    },
]

# ─────────────────────────────────────────────────────────────────────────────

class BenchmarkTracker:
    def __init__(self, name):
        self.name             = name
        self.latency_total_ms = 0
        self.latency_tavily_ms = 0
        self.tavily_calls     = 0
        self.tavily_cache_hit = False
        self.tokens_prompt    = 0
        self.tokens_completion = 0
        self.tokens_total     = 0
        self.estimated_cost   = 0.0
        self.candidates       = 0
        self.avg_score        = 0.0
        self.pydantic_failures = 0

    def compute_cost(self):
        self.estimated_cost = round(
            (self.tokens_prompt     / 1_000_000) * 0.59 +
            (self.tokens_completion / 1_000_000) * 0.79, 6,
        )

    def report(self):
        return {
            "scenario":           self.name,
            "approach":           "C — Tavily + LLM Groq",
            "latency_total_ms":   self.latency_total_ms,
            "latency_tavily_ms":  self.latency_tavily_ms,
            "tavily_calls":       self.tavily_calls,
            "tavily_cache_hit":   self.tavily_cache_hit,
            "tokens_prompt":      self.tokens_prompt,
            "tokens_completion":  self.tokens_completion,
            "tokens_total":       self.tokens_total,
            "estimated_cost_usd": self.estimated_cost,
            "candidates_returned": self.candidates,
            "avg_match_score":    self.avg_score,
            "pydantic_failures":  self.pydantic_failures,
        }

# ─────────────────────────────────────────────────────────────────────────────

def validate(result, scenario):
    errors = []
    if "restaurant_candidates" not in result:
        errors.append("clé 'restaurant_candidates' manquante"); return errors
    candidates = result["restaurant_candidates"]
    if not isinstance(candidates, list):
        errors.append(f"pas une liste : {type(candidates)}"); return errors
    if scenario["expect_empty"] and candidates:
        errors.append(f"vide attendu — {len(candidates)} reçus"); return errors
    if not candidates:
        return errors
    scores = [c.get("match_score", 0) for c in candidates]
    if scores != sorted(scores, reverse=True):
        errors.append(f"non trié par match_score : {scores}")
    for i, c in enumerate(candidates):
        for f in REQUIRED_FIELDS:
            if f not in c: errors.append(f"candidat[{i}] champ manquant : '{f}'")
        if not c.get("id"): errors.append(f"candidat[{i}] id vide")
        s = c.get("match_score")
        if s is None or not (0.0 <= s <= 1.0): errors.append(f"candidat[{i}] match_score hors [0,1]")
        if c.get("tier") not in VALID_TIERS:    errors.append(f"candidat[{i}] tier invalide : {c.get('tier')!r}")
        r = c.get("rating")
        if r is not None and not (1.0 <= r <= 5.0): errors.append(f"candidat[{i}] rating hors [1,5]")
    return errors

# ─────────────────────────────────────────────────────────────────────────────

def run():
    node        = RestaurantNodeC()
    total_pass  = 0
    total_fail  = 0
    all_reports = []

    for scenario in SCENARIOS:
        print(f"\n{'=' * 70}")
        print(f"SCENARIO {scenario['name']}")
        print("=" * 70)

        tracker = BenchmarkTracker(scenario["name"])
        state   = scenario["state"]

        # Invalider le cache Tavily pour mesure à froid
        cache.invalidate_prefix("tavily_rest_")
        cache.invalidate_prefix("node_cache:restaurant_node_c")

        # Appel node (à froid — Tavily réel)
        t0     = time.time()
        result = node.run(state)
        tracker.latency_total_ms = int((time.time() - t0) * 1000)

        candidates = result.get("restaurant_candidates", [])
        tracker.candidates = len(candidates)
        if candidates:
            tracker.avg_score = round(sum(c.get("match_score", 0) for c in candidates) / len(candidates), 4)

        # Récupérer métriques depuis le node
        tracker.tavily_calls      = node._last_benchmark.get("tavily_calls", 0)
        tracker.tavily_cache_hit  = node._last_benchmark.get("cache_hit", False)
        tracker.latency_tavily_ms = node._last_benchmark.get("latency_ms", 0)

        # Appel 2ème (cache chaud) pour capturer tokens
        node.run(state)
        tracker.tokens_prompt     = node._last_tokens.get("prompt", 0)
        tracker.tokens_completion = node._last_tokens.get("completion", 0)
        tracker.tokens_total      = node._last_tokens.get("total", 0)
        tracker.compute_cost()

        # Affichage
        print(f"  candidats     : {len(candidates)}")
        print(f"  latence total : {tracker.latency_total_ms}ms  (tavily={tracker.latency_tavily_ms}ms)")
        print(f"  tavily        : calls={tracker.tavily_calls} | cache={'HIT' if tracker.tavily_cache_hit else 'MISS'}")
        print(f"  tokens        : prompt={tracker.tokens_prompt} | completion={tracker.tokens_completion} | total={tracker.tokens_total}")
        print(f"  coût est.     : ${tracker.estimated_cost:.6f}")

        for c in candidates[:5]:
            reason = (c.get("recommendation_reason") or "")[:60]
            print(
                f"    [{c.get('tier','?'):10}] "
                f"{c.get('name','?')[:35]:<35} "
                f"⭐{c.get('rating') or '?'} "
                f"score={c.get('match_score', 0):.2f} "
                f"| {reason}"
            )
        if len(candidates) > 5:
            print(f"    ... (+{len(candidates) - 5} autres)")

        errs = validate(result, scenario)
        if errs:
            total_fail += 1
            print(f"  [FAIL] {len(errs)} erreur(s):")
            for e in errs: print(f"    - {e}")
        else:
            total_pass += 1
            print(f"  [PASS]")

        all_reports.append(tracker.report())

    print(f"\n{'=' * 70}")
    print(f"RÉSULTATS : {total_pass} PASS / {total_fail} FAIL sur {len(SCENARIOS)} scénarios")
    print(f"TOKENS TOTAL    : {sum(r['tokens_total'] for r in all_reports)}")
    print(f"COÛT ESTIMÉ     : ${sum(r['estimated_cost_usd'] for r in all_reports):.6f}")
    print(f"TAVILY CALLS    : {sum(r['tavily_calls'] for r in all_reports)}")
    print("=" * 70)
    print("\n── BENCHMARK (JSON) ──")
    print(json.dumps(all_reports, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    run()
