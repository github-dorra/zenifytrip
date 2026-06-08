"""
Script autonome — sauvegarde les résultats du benchmark restaurant A vs B vs C
sans relancer les tests.
Résultats issus du run du 2026-06-07.

Usage : python scripts/save_benchmark_results.py
"""

import os
import json
from datetime import datetime

# ─────────────────────────────────────────────────────────────────────────────
# Résultats connus — dernière exécution de test_compare_abc.py (2026-06-07)
# ─────────────────────────────────────────────────────────────────────────────

BENCHMARK_DATE    = "2026-06-07T12:09:00"
BENCHMARK_VERSION = "1.0"

SUMMARY = {
    "A": {
        "total_candidates": 58,
        "avg_latency_ms":   1361,
        "total_cost_usd":   0.0,
        "total_tokens":     0,
        "scenarios_won":    6,
        "hallucination_pct": 0,
    },
    "B": {
        "total_candidates": 14,
        "avg_latency_ms":   4397,
        "total_cost_usd":   0.00428,
        "total_tokens":     9151,
        "scenarios_won":    0,
        "hallucination_pct": 46,
    },
    "C": {
        "total_candidates": 26,
        "avg_latency_ms":   7607,
        "total_cost_usd":   0.00777,
        "total_tokens":     11938,
        "scenarios_won":    0,
        "hallucination_pct": 0,
    },
}

SCENARIOS = [
    {
        "scenario": "1 — Sousse | seafood | medium",
        "A": {"candidates": 10, "latency_ms": 1666, "has_rating_pct": 100.0, "has_coords_pct": 100.0, "has_reason_pct": 0.0,   "cost_usd": 0.0},
        "B": {"candidates": 3,  "latency_ms": 1521, "has_rating_pct": 100.0, "has_coords_pct": 0.0,   "has_reason_pct": 100.0, "cost_usd": 0.000997},
        "C": {"candidates": 5,  "latency_ms": 3515, "has_rating_pct": 40.0,  "has_coords_pct": 0.0,   "has_reason_pct": 100.0, "cost_usd": 0.00128},
    },
    {
        "scenario": "2 — Djerba | famille | medium",
        "A": {"candidates": 10, "latency_ms": 1229, "has_rating_pct": 100.0, "has_coords_pct": 100.0, "has_reason_pct": 0.0,   "cost_usd": 0.0},
        "B": {"candidates": 3,  "latency_ms": 1504, "has_rating_pct": 100.0, "has_coords_pct": 0.0,   "has_reason_pct": 100.0, "cost_usd": 0.000975},
        "C": {"candidates": 7,  "latency_ms": 8454, "has_rating_pct": 42.9,  "has_coords_pct": 0.0,   "has_reason_pct": 100.0, "cost_usd": 0.001479},
    },
    {
        "scenario": "3 — Tunis | cuisine locale | medium",
        "A": {"candidates": 10, "latency_ms": 1669, "has_rating_pct": 100.0, "has_coords_pct": 100.0, "has_reason_pct": 0.0,   "cost_usd": 0.0},
        "B": {"candidates": 3,  "latency_ms": 7681, "has_rating_pct": 100.0, "has_coords_pct": 0.0,   "has_reason_pct": 100.0, "cost_usd": 0.001},
        "C": {"candidates": 4,  "latency_ms": 8066, "has_rating_pct": 0.0,   "has_coords_pct": 0.0,   "has_reason_pct": 100.0, "cost_usd": 0.001158},
    },
    {
        "scenario": "4 — Exploratory | pas de destination",
        "A": {"candidates": 10, "latency_ms": 1141, "has_rating_pct": 100.0, "has_coords_pct": 100.0, "has_reason_pct": 0.0,   "cost_usd": 0.0},
        "B": {"candidates": 3,  "latency_ms": 6702, "has_rating_pct": 100.0, "has_coords_pct": 0.0,   "has_reason_pct": 100.0, "cost_usd": 0.001001},
        "C": {"candidates": 3,  "latency_ms": 7531, "has_rating_pct": 0.0,   "has_coords_pct": 0.0,   "has_reason_pct": 100.0, "cost_usd": 0.001029},
    },
    {
        "scenario": "5 — Destination inconnue | fallback",
        "A": {"candidates": 7,  "latency_ms": 1143, "has_rating_pct": 100.0, "has_coords_pct": 100.0, "has_reason_pct": 0.0,   "cost_usd": 0.0},
        "B": {"candidates": 0,  "latency_ms": 2712, "has_rating_pct": 0.0,   "has_coords_pct": 0.0,   "has_reason_pct": 0.0,   "cost_usd": 0.0},
        "C": {"candidates": 0,  "latency_ms": 7897, "has_rating_pct": 0.0,   "has_coords_pct": 0.0,   "has_reason_pct": 0.0,   "cost_usd": 0.0},
    },
    {
        "scenario": "6 — Monastir | luxury romantique",
        "A": {"candidates": 10, "latency_ms": 1269, "has_rating_pct": 100.0, "has_coords_pct": 100.0, "has_reason_pct": 0.0,   "cost_usd": 0.0},
        "B": {"candidates": 3,  "latency_ms": 4833, "has_rating_pct": 100.0, "has_coords_pct": 0.0,   "has_reason_pct": 100.0, "cost_usd": 0.001037},
        "C": {"candidates": 3,  "latency_ms": 7694, "has_rating_pct": 0.0,   "has_coords_pct": 0.0,   "has_reason_pct": 100.0, "cost_usd": 0.001008},
    },
]

# ─────────────────────────────────────────────────────────────────────────────

def save():
    bench_dir = os.path.join(os.path.dirname(__file__), "..", "app", "data", "benchmarks")
    os.makedirs(bench_dir, exist_ok=True)

    # ── JSON ──────────────────────────────────────────────────────────
    data = {
        "benchmark_date":    BENCHMARK_DATE,
        "benchmark_version": BENCHMARK_VERSION,
        "total_scenarios":   len(SCENARIOS),
        "summary":           SUMMARY,
        "verdict":           "A_winner",
        "scenarios":         SCENARIOS,
    }

    json_path = os.path.join(bench_dir, "restaurant_benchmark_results.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    # ── TXT ───────────────────────────────────────────────────────────
    sA, sB, sC = SUMMARY["A"], SUMMARY["B"], SUMMARY["C"]
    n = len(SCENARIOS)

    txt = f"""BENCHMARK RESTAURANT — ZenifyTrip
Date : {BENCHMARK_DATE}
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
Raison             : volume maximal, données structurées (coords GPS 100%,
                     ratings 100%), gratuit ($0), ranking_node LLM
                     en aval génère recommendation_reason
Rejet B            : 46% hallucination = inacceptable pour système commercial
Rejet C seul       : lent, données partielles, fragile (quota Tavily)
Date de décision   : {BENCHMARK_DATE[:10]}

Fichiers résultats :
  app/data/benchmarks/restaurant_benchmark_results.json
  app/data/benchmarks/restaurant_benchmark_summary.txt
═══════════════════════════════════
"""

    txt_path = os.path.join(bench_dir, "restaurant_benchmark_summary.txt")
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(txt)

    print(f"Sauvegarde terminée :")
    print(f"  JSON : {os.path.abspath(json_path)}")
    print(f"  TXT  : {os.path.abspath(txt_path)}")


if __name__ == "__main__":
    save()
