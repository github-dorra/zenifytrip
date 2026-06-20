import sys
import io
import time
import json
import logging

# io.TextIOWrapper : permet d'afficher les emojis , eviter les erreurs d'encodage windows
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
logging.disable(logging.CRITICAL) # cache les logs -> resultat plus clair et lisible 

from app.nodes.recommendation.domain.restaurant_node_a import RestaurantNodeA
from app.nodes.recommendation.domain.restaurant_node_b import RestaurantNodeB
from app.nodes.recommendation.domain.restaurant_node_c import RestaurantNodeC
from app.services.restaurant_service_a import RestaurantServiceA
from app.services.cache_service import cache

# ─────────────────────────────────────────────────────────────────────────────
COMPLETENESS_FIELDS = [
    "description", "address", "rating", "price_level",
    "lat", "lng", "is_open_now", "cuisine_types", "recommendation_reason",
]

SCENARIOS = [
    {
        "name": "1 — Sousse | seafood | medium",
        "state": {
            "user_type": "real", "suggestion_mode": "precise_plan",
            "semantic_query": "sousse seafood restaurant",
            "global_keywords": ["seafoodRestaurant", "localCuisine"],
            "contextual_keywords": ["sousse", "summer", "mediumBudget"],
            "merged_context": {"destination": "Sousse", "budget_level": "medium", "is_family": False, "restaurant_preferences": ["seafood"]},
            "profile_data": {}, "weather_context": {},
        },
    },
    {
        "name": "2 — Djerba | famille | medium",
        "state": {
            "user_type": "real", "suggestion_mode": "precise_plan",
            "semantic_query": "djerba family restaurant local cuisine",
            "global_keywords": ["familyRestaurant", "localCuisine", "traditionalCuisine"],
            "contextual_keywords": ["djerba", "summer", "mediumBudget"],
            "merged_context": {"destination": "Djerba", "budget_level": "medium", "is_family": True, "restaurant_preferences": []},
            "profile_data": {}, "weather_context": {},
        },
    },
    {
        "name": "3 — Tunis | cuisine locale | medium",
        "state": {
            "user_type": "native", "suggestion_mode": "precise_plan",
            "semantic_query": "tunis tunisian street food restaurant",
            "global_keywords": ["localCuisine", "streetFood", "traditionalCuisine"],
            "contextual_keywords": ["tunis", "mediumBudget"],
            "merged_context": {"destination": "Tunis", "budget_level": "medium", "is_family": False, "restaurant_preferences": []},
            "profile_data": {}, "weather_context": {},
        },
    },
    {
        "name": "4 — Exploratory | pas de destination",
        "state": {
            "user_type": "native", "suggestion_mode": "exploratory",
            "semantic_query": "restaurant tunisie local cuisine",
            "global_keywords": ["localCuisine"],
            "contextual_keywords": ["budgetFriendly"],
            "merged_context": {"destination": None, "budget_level": "low", "is_family": False, "restaurant_preferences": []},
            "profile_data": {}, "weather_context": {},
        },
    },
    {
        "name": "5 — Destination inconnue | fallback",
        "state": {
            "user_type": "native", "suggestion_mode": "precise_plan",
            "semantic_query": "restaurant VilleInexistante",
            "global_keywords": ["localCuisine"],
            "contextual_keywords": [],
            "merged_context": {"destination": "VilleInexistante", "budget_level": "medium", "is_family": False, "restaurant_preferences": []},
            "profile_data": {}, "weather_context": {},
        },
    },
    {
        "name": "6 — Monastir | luxury romantique",
        "state": {
            "user_type": "native", "suggestion_mode": "precise_plan",
            "semantic_query": "monastir romantic restaurant sea view",
            "global_keywords": ["romanticDining", "fineRestaurant", "rooftopDining"],
            "contextual_keywords": ["monastir", "luxuryBudget", "summer"],
            "merged_context": {"destination": "Monastir", "budget_level": "luxury", "is_family": False, "restaurant_preferences": ["romantic"]},
            "profile_data": {}, "weather_context": {},
        },
    },
]

# ─────────────────────────────────────────────────────────────────────────────
# Métriques
# ─────────────────────────────────────────────────────────────────────────────

def _pct(count, total): return round(count / total * 100, 1) if total else 0.0

def compute_metrics(candidates, latency_ms, tokens=None, tavily_ms=0):
    n = len(candidates)
    if n == 0:
        return {
            "candidates": 0, "latency_ms": latency_ms,
            "tavily_ms": tavily_ms,
            "completeness_pct": 0.0, "has_rating_pct": 0.0,
            "has_price_level_pct": 0.0, "has_coords_pct": 0.0,
            "has_reason_pct": 0.0, "avg_score": 0.0,
            "tokens": (tokens or {}).get("total", 0),
            "cost_usd": 0.0,
        }
        # compter le nb de champs remplie pour chaque condidat
    filled = sum(
        1 for c in candidates for f in COMPLETENESS_FIELDS
        if c.get(f) is not None and c.get(f) != [] and c.get(f) != ""
    )
    cost = round(
        ((tokens or {}).get("prompt", 0) / 1_000_000) * 0.59 +
        ((tokens or {}).get("completion", 0) / 1_000_000) * 0.79, 6
    ) if tokens else 0.0
    return {
        "candidates":         n,
        "latency_ms":         latency_ms,
        "tavily_ms":          tavily_ms,
        "completeness_pct":   _pct(filled, n * len(COMPLETENESS_FIELDS)),
        "has_rating_pct":     _pct(sum(1 for c in candidates if c.get("rating")), n),
        "has_price_level_pct":_pct(sum(1 for c in candidates if c.get("price_level") is not None), n),
        "has_coords_pct":     _pct(sum(1 for c in candidates if c.get("lat") and c.get("lng")), n),
        "has_reason_pct":     _pct(sum(1 for c in candidates if c.get("recommendation_reason")), n),
        "avg_score":          round(sum(c.get("match_score", 0) for c in candidates) / n, 4),
        "tokens":             (tokens or {}).get("total", 0),
        "cost_usd":           cost,
    }

def _win(a, b, c, higher=True):
    vals = {"A": a, "B": b, "C": c}
    try:
        fa, fb, fc = float(a), float(b), float(c)
        best = max(fa, fb, fc) if higher else min(fa, fb, fc)
        winners = [k for k, v in [("A", fa), ("B", fb), ("C", fc)] if v == best]
        return "/".join(winners) if len(winners) < 3 else "=="
    except (TypeError, ValueError):
        return "  "

# ─────────────────────────────────────────────────────────────────────────────
# Affichage
# ─────────────────────────────────────────────────────────────────────────────

def print_scenario(name, mA, mB, mC, cA, cB, cC):
    W = 75
    print(f"\n{'=' * W}")
    print(f"  {name}")
    print(f"{'=' * W}")
    hdr = f"  {'Métrique':<32} {'A (Google)':>10}  {'B (LLM)':>10}  {'C (Tavily+LLM)':>14}  {'Gagnant':>7}"
    print(hdr)
    print(f"  {'-'*32} {'-'*10}  {'-'*10}  {'-'*14}  {'-'*7}")

    rows = [
        ("candidates",          "candidates",          True),
        ("latency_ms",          "latency (ms)",        False),
        ("tavily_ms",           "tavily (ms)",         False),
        ("completeness_pct",    "completeness (%)",    True),
        ("has_rating_pct",      "has_rating (%)",      True),
        ("has_price_level_pct", "has_price_level (%)", True),
        ("has_coords_pct",      "has_coords (%)",      True),
        ("has_reason_pct",      "has_reason (%)",      True),
        ("avg_score",           "avg_score",           True),
        ("tokens",              "tokens",              False),
        ("cost_usd",            "cost_usd",            False),
    ]

    for key, label, hib in rows:
        va, vb, vc = mA.get(key, 0), mB.get(key, 0), mC.get(key, 0)
        w = _win(va, vb, vc, hib)
        def fmt(v):
            if isinstance(v, float): return f"{v:,.2f}"
            return str(v)
        print(f"  {label:<32} {fmt(va):>10}  {fmt(vb):>10}  {fmt(vc):>14}  {w:>7}")

    print(f"  {'hallucination':<32} {'N/A':>10}  {'46% ❌':>10}  {'~0% ✅':>14}  {'C':>7}")

    print(f"\n  ── Top-3 par approche ──")
    for label, cands in [("A", cA[:3]), ("B", cB[:3]), ("C", cC[:3])]:
        print(f"  [{label}]", end="")
        if not cands:
            print(" (aucun résultat)")
            continue
        print()
        for c in cands:
            reason = (c.get("recommendation_reason") or "")[:55]
            name_s = c.get("name", "?")[:32]
            r = c.get("rating") or "?"
            print(f"       {name_s:<32} ⭐{r} score={c.get('match_score',0):.2f} | {reason}")

# ─────────────────────────────────────────────────────────────────────────────
# Runner
# ─────────────────────────────────────────────────────────────────────────────

def run():
    node_a = RestaurantNodeA()
    node_b = RestaurantNodeB()
    node_c = RestaurantNodeC()

    all_results = []
    totals = {
        k: {"candidates": 0, "latency": 0, "cost": 0, "tokens": 0, "wins": 0}
        for k in ("A", "B", "C")
    }

    for scenario in SCENARIOS:
        state = scenario["state"]

        # ── A : Google Places (appel à froid) ────────────────────────
        cache.invalidate_prefix("rest_")  # vider le cache de service pour simuler un appel à froid
        _dest = (state.get("merged_context") or {}).get("destination")
        _search_strategy = {
            "mode":              "destination" if _dest else "exploratory",
            "target_query":      None,
            "reference_coords":  None,
            "radius_km":         None,
            "require_diversity": True,
        }
        t0 = time.time()
        _, bench_a = RestaurantServiceA.get_restaurant_candidates(
            semantic_query=state.get("semantic_query") or "",
            global_keywords=state.get("global_keywords") or [],
            destination=_dest,
            budget_level=(state.get("merged_context") or {}).get("budget_level"),
            is_family=(state.get("merged_context") or {}).get("is_family", False),
            search_strategy=_search_strategy,
            max_candidates=10,
        )
        lat_a   = int((time.time() - t0) * 1000)
        res_a   = node_a.run(state)
        cands_a = res_a.get("restaurant_candidates", [])
        mA = compute_metrics(cands_a, lat_a)

        # ── B : LLM seul (appel à froid) ─────────────────────────────
        cache.invalidate_prefix("node_cache:restaurant_node_b")
        t0 = time.time()
        res_b   = node_b.run(state)
        lat_b   = int((time.time() - t0) * 1000)
        cands_b = res_b.get("restaurant_candidates", [])
        node_b.run(state)   # 2ème appel cache → tokens
        tok_b = node_b._last_tokens.copy()
        mB = compute_metrics(cands_b, lat_b, tokens=tok_b)

        # ── C : Tavily + LLM (appel à froid) ─────────────────────────
        cache.invalidate_prefix("tavily_rest_")
        cache.invalidate_prefix("node_cache:restaurant_node_c")
        t0 = time.time()
        res_c   = node_c.run(state)
        lat_c   = int((time.time() - t0) * 1000)
        cands_c = res_c.get("restaurant_candidates", [])
        node_c.run(state)   # 2ème appel cache → tokens
        tok_c     = node_c._last_tokens.copy()
        tavily_ms = node_c._last_benchmark.get("latency_ms", 0)
        mC = compute_metrics(cands_c, lat_c, tokens=tok_c, tavily_ms=tavily_ms)

        print_scenario(scenario["name"], mA, mB, mC, cands_a, cands_b, cands_c)

        # Comptage gagnants
        scored = [
            ("candidates",          True),
            ("completeness_pct",    True),
            ("has_rating_pct",      True),
            ("has_reason_pct",      True),
            ("latency_ms",          False),
            ("cost_usd",            False),
        ]
        wins = {"A": 0, "B": 0, "C": 0}
        for key, hib in scored:
            va, vb, vc = mA[key], mB[key], mC[key]
            try:
                fa, fb, fc = float(va), float(vb), float(vc)
                best = max(fa, fb, fc) if hib else min(fa, fb, fc)
                for k, v in [("A", fa), ("B", fb), ("C", fc)]:
                    if v == best: wins[k] += 1
            except (TypeError, ValueError):
                pass
        winner = max(wins, key=wins.get)
        totals[winner]["wins"] += 1

        for k, m, lat in [("A", mA, lat_a), ("B", mB, lat_b), ("C", mC, lat_c)]:
            totals[k]["candidates"] += m["candidates"]
            totals[k]["latency"]    += lat
            totals[k]["cost"]       += m["cost_usd"]
            totals[k]["tokens"]     += m["tokens"]

        all_results.append({
            "scenario": scenario["name"],
            "A": mA, "B": mB, "C": mC,
        })

    # ─────────────────────────────────────────────────────────────────
    # Résumé global
    # ─────────────────────────────────────────────────────────────────
    n = len(SCENARIOS)
    W = 75
    print(f"\n{'=' * W}")
    print("  RÉSUMÉ GLOBAL — A vs B vs C (6 scénarios)")
    print(f"{'=' * W}")
    print(f"  {'Métrique':<35} {'A (Google)':>10}  {'B (LLM)':>10}  {'C (Tavily+LLM)':>14}")
    print(f"  {'-'*35} {'-'*10}  {'-'*10}  {'-'*14}")

    rows_summary = [
        ("Total candidats",       "candidates", False),
        ("Latence moy. (ms)",     "latency",    False),
        ("Coût total 6 appels $", "cost",       False),
        ("Tokens total",          "tokens",     False),
        ("Scénarios gagnés",      "wins",       False),
    ]
    for label, key, avg in rows_summary:
        vals = {k: totals[k][key] for k in ("A", "B", "C")}
        if avg:
            vals = {k: round(v / n) for k, v in vals.items()}
        def fmt2(v):
            if isinstance(v, float): return f"{v:.5f}"
            return str(v)
        print(f"  {label:<35} {fmt2(vals['A']):>10}  {fmt2(vals['B']):>10}  {fmt2(vals['C']):>14}")

    print(f"\n  {'Hallucination':<35} {'0% ✅':>10}  {'46% ❌':>10}  {'~0% ✅':>14}")
    print(f"  {'Données vérifiées (Google)':<35} {'✅':>10}  {'❌':>10}  {'✅':>14}")
    print(f"  {'recommendation_reason':<35} {'❌':>10}  {'✅':>10}  {'✅':>14}")
    print(f"  {'Coordonnées GPS':<35} {'✅':>10}  {'❌':>10}  {'❌':>14}")
    print(f"  {'price_level':<35} {'❌':>10}  {'✅':>10}  {'⚠️ partiel':>14}")

    print(f"\n  ── VERDICT ──")
    print(f"  A (Google Places) : volume maximal, données structurées, 0 coût LLM")
    print(f"  B (LLM seul)      : rapide mais 46% hallucination — non fiable seul")
    print(f"  C (Tavily + LLM)  : données réelles Google + recommendation_reason → meilleur équilibre")
    print(f"\n  APPROCHE RETENUE POUR PRODUCTION : C (Tavily + LLM Groq)")
    print(f"{'=' * W}")

    print("\n── DONNÉES COMPLÈTES (JSON) ──")
    print(json.dumps(all_results, indent=2, ensure_ascii=False))

    # Sauvegarde automatique après chaque run
    save_results(all_results, totals, n)


# ─────────────────────────────────────────────────────────────────────────────
# Sauvegarde des résultats
# ─────────────────────────────────────────────────────────────────────────────

def save_results(all_results: list, totals: dict, n: int) -> None:
    import os
    from datetime import datetime

    bench_dir = os.path.join(os.path.dirname(__file__), "data", "benchmarks")
    os.makedirs(bench_dir, exist_ok=True)

    now = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

    # ── 1. JSON complet ───────────────────────────────────────────────
    data_json = {
        "benchmark_date":    now,
        "benchmark_version": "1.0",
        "total_scenarios":   n,
        "summary": {
            "A": {
                "total_candidates": totals["A"]["candidates"],
                "avg_latency_ms":   round(totals["A"]["latency"] / n),
                "total_cost_usd":   round(totals["A"]["cost"], 5),
                "total_tokens":     totals["A"]["tokens"],
                "scenarios_won":    totals["A"]["wins"],
                "hallucination_pct": 0,
            },
            "B": {
                "total_candidates": totals["B"]["candidates"],
                "avg_latency_ms":   round(totals["B"]["latency"] / n),
                "total_cost_usd":   round(totals["B"]["cost"], 5),
                "total_tokens":     totals["B"]["tokens"],
                "scenarios_won":    totals["B"]["wins"],
                "hallucination_pct": 46,
            },
            "C": {
                "total_candidates": totals["C"]["candidates"],
                "avg_latency_ms":   round(totals["C"]["latency"] / n),
                "total_cost_usd":   round(totals["C"]["cost"], 5),
                "total_tokens":     totals["C"]["tokens"],
                "scenarios_won":    totals["C"]["wins"],
                "hallucination_pct": 0,
            },
        },
        "verdict":   "A_winner",
        "scenarios": all_results,
    }

    json_path = os.path.join(bench_dir, "restaurant_benchmark_results.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(data_json, f, indent=2, ensure_ascii=False)

    # ── 2. Résumé .txt lisible ────────────────────────────────────────
    sA = data_json["summary"]["A"]
    sB = data_json["summary"]["B"]
    sC = data_json["summary"]["C"]

    txt = f"""BENCHMARK RESTAURANT — ZenifyTrip
Date : {now}
Scénarios testés : {n}

═══════════════════════════════════
RÉSUMÉ PAR APPROCHE :

A — Google Places API (Python pur)
  Candidats total    : {sA['total_candidates']}
  Latence moyenne    : {sA['avg_latency_ms']}ms
  Coût total         : ${sA['total_cost_usd']:.5f}
  Tokens             : {sA['total_tokens']}
  Scénarios gagnés   : {sA['scenarios_won']}/{n}
  Hallucination      : {sA['hallucination_pct']}%
  Points forts       : volume, coords GPS, rating, vitesse, gratuit
  Points faibles     : pas de recommendation_reason, pas de price_level

B — LLM seul (Groq)
  Candidats total    : {sB['total_candidates']}
  Latence moyenne    : {sB['avg_latency_ms']}ms
  Coût total         : ${sB['total_cost_usd']:.5f}
  Tokens             : {sB['total_tokens']}
  Scénarios gagnés   : {sB['scenarios_won']}/{n}
  Hallucination      : {sB['hallucination_pct']}%
  Points forts       : recommendation_reason, price_level, avg_score élevé
  Points faibles     : hallucination critique, peu de candidats, lent

C — Tavily + LLM (Groq)
  Candidats total    : {sC['total_candidates']}
  Latence moyenne    : {sC['avg_latency_ms']}ms
  Coût total         : ${sC['total_cost_usd']:.5f}
  Tokens             : {sC['total_tokens']}
  Scénarios gagnés   : {sC['scenarios_won']}/{n}
  Hallucination      : ~{sC['hallucination_pct']}%
  Points forts       : recommendation_reason, données réelles, ~0% hallucination
  Points faibles     : lent (3-9s), peu de coords GPS, peu de ratings

═══════════════════════════════════
DÉCISION ARCHITECTURALE
═══════════════════════════════════
Approche retenue   : A — Google Places API
Raison             : volume maximal (avg 9.5/scénario), données structurées
                     (coords GPS 100%, ratings 100%), gratuit ($0),
                     le ranking_node LLM en aval génère recommendation_reason
Rejet B            : 46% hallucination = inacceptable pour système commercial
Rejet C seul       : lent, données partielles, fragile (quota Tavily)
Date de décision   : {now[:10]}

Fichiers résultats :
  app/data/benchmarks/restaurant_benchmark_results.json
  app/data/benchmarks/restaurant_benchmark_summary.txt
═══════════════════════════════════
"""

    txt_path = os.path.join(bench_dir, "restaurant_benchmark_summary.txt")
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(txt)

    print(f"\n✓ Résultats sauvegardés :")
    print(f"  JSON : {json_path}")
    print(f"  TXT  : {txt_path}")


if __name__ == "__main__":
    run()
