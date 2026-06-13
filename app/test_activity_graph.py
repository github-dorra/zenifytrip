"""
Test end-to-end graphe complet — intention activité
====================================================
Lance le pipeline Phase 1→4 avec un message de type activity_recommendation.
Vérifie : compilation graphe, routing orchestrateur, activity_node, data_merger.
"""
import sys
import io
import json
import time
import uuid

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from app.graph.builder import build_graph
from app.graph.state import build_initial_state

# ─── Scénarios ───────────────────────────────────────────────────────────────

SCENARIOS = [
    {
        "name": "1 — USER RÉEL | activités Sousse | precise_plan",
        "user_id":    "2720b441-6e48-464f-880b-71dd2d4cdca5",
        "message":    "je voudrais faire des activités culturelles à Sousse demain",
        "expect_intent": "activity_recommendation",
    },
    {
        "name": "2 — USER NATIF | activités Djerba famille",
        "user_id":    "00000000-0000-0000-0000-000000000000",
        "message":    "quelles activités peut-on faire en famille à Djerba ?",
        "expect_intent": "activity_recommendation",
    },
    {
        "name": "3 — USER NATIF | day_planning Hammamet",
        "user_id":    "00000000-0000-0000-0000-000000000000",
        "message":    "planifie-moi une journée complète à Hammamet avec activités et restaurants",
        "expect_intent": "day_planning",
    },
]

# ─── Helpers ─────────────────────────────────────────────────────────────────

def print_section(title: str):
    print(f"\n{'─'*60}")
    print(f"  {title}")
    print('─'*60)

def check(label: str, condition: bool, detail: str = ""):
    status = "PASS" if condition else "FAIL"
    suffix = f"  ({detail})" if detail else ""
    print(f"  [{status}] {label}{suffix}")
    return condition

# ─── Runner ──────────────────────────────────────────────────────────────────

def run_scenario(graph, scenario: dict) -> dict:
    print_section(scenario["name"])

    state = build_initial_state(
        user_message=scenario["message"],
        session_id=str(uuid.uuid4()),
        user_id=scenario["user_id"],
    )
    # errors doit être une liste (Annotated operator.add)
    state["errors"] = []
    state["node_metrics"] = []

    t0 = time.time()
    try:
        result = graph.invoke(state)
    except Exception as e:
        print(f"  [ERROR] graph.invoke échoué : {e}")
        import traceback; traceback.print_exc()
        return {}
    duration = round(time.time() - t0, 2)

    # ── Extraction résultats ──────────────────────────────────────────
    intent_result   = result.get("intent_result") or {}
    primary_intent  = intent_result.get("primary_intent", "—")
    constraints     = intent_result.get("constraints") or {}

    merged          = result.get("merged_context") or {}
    availability    = result.get("availability_result") or {}
    requested_svcs  = result.get("requested_services") or []
    activity_cands  = result.get("activity_candidates") or []
    final_answer    = result.get("final_answer") or ""
    errors          = result.get("errors") or []

    # ── Affichage ────────────────────────────────────────────────────
    print(f"\n  Message      : {scenario['message']}")
    print(f"  Durée totale : {duration}s")

    print(f"\n  Intent détecté    : {primary_intent}")
    print(f"  Action type       : {intent_result.get('action_type')}")
    print(f"  Destination       : {constraints.get('destination') or merged.get('destination')}")
    print(f"  Suggestion mode   : {result.get('suggestion_mode')}")
    print(f"  is_on_trip        : {merged.get('is_on_trip')}")
    print(f"  days_remaining    : {merged.get('days_remaining')}")
    print(f"  hotel_name        : {merged.get('hotel_name')}")
    print(f"  Requested services: {requested_svcs}")

    print(f"\n  availability_result:")
    print(f"    trip_is_ongoing     = {availability.get('trip_is_ongoing')}")
    print(f"    booked_activity_ids = {availability.get('booked_activity_ids', [])}")

    print(f"\n  Activity candidates : {len(activity_cands)}")
    for i, c in enumerate(activity_cands[:5]):
        src   = c.get("source", "?")
        tier  = c.get("tier", "?")
        score = c.get("score", 0)
        atype = c.get("activity_type", "?")
        avail = "✓" if c.get("is_available") else "✗"
        print(f"    [{i+1}] {c.get('name', '—')[:45]:<45} | {src:<9} | {tier:<8} | type={atype:<15} | score={score:.3f} | avail={avail}")

    if errors:
        print(f"\n  Errors ({len(errors)}) :")
        for e in errors:
            print(f"    - {e}")

    print(f"\n  Final answer (extrait) :")
    print(f"    {final_answer[:300] if final_answer else '—'}")

    # ── Checks ───────────────────────────────────────────────────────
    print(f"\n  Checks :")
    passed = 0
    total  = 0

    def chk(label, cond, detail=""):
        nonlocal passed, total
        total += 1
        ok = check(label, cond, detail)
        if ok: passed += 1
        return ok

    chk("intent correct",        primary_intent == scenario["expect_intent"],
        f"got={primary_intent}, expected={scenario['expect_intent']}")
    chk("activity_node activé",  "activity_node" in requested_svcs or len(activity_cands) > 0,
        f"requested_services={requested_svcs}")
    chk("au moins 1 candidat",   len(activity_cands) > 0)
    chk("final_answer non vide", len(final_answer) > 20)
    chk("aucune erreur critique", len(errors) == 0, f"{len(errors)} erreurs")

    print(f"\n  Résultat : {passed}/{total} checks PASS")
    return result


def main():
    print("\n" + "="*60)
    print("  TEST END-TO-END — activity_recommendation")
    print("="*60)

    print("\nCompilation du graphe...")
    try:
        graph = build_graph()
        print("  Graphe compilé OK")
    except Exception as e:
        print(f"  ERREUR compilation : {e}")
        import traceback; traceback.print_exc()
        return

    total_pass = 0
    total_fail = 0

    for scenario in SCENARIOS:
        result = run_scenario(graph, scenario)
        # on compte juste si le résultat est non vide
        if result:
            total_pass += 1
        else:
            total_fail += 1

    print("\n" + "="*60)
    print(f"  BILAN : {total_pass}/{len(SCENARIOS)} scénarios exécutés")
    print("="*60 + "\n")


if __name__ == "__main__":
    main()
