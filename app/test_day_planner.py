"""
test_day_planner.py
────────────────────────────────────────────────────────────────────────────
Test ciblé du day_planner_node — vérifie le prompt V2.

Checks automatiques :
  - itinerary généré (non null)
  - duration_days correspond au nombre de jours produits
  - aucun candidate_id dupliqué entre les jours (Rule 12)
  - titres de jours tous différents (Rule 11)
  - tous les time_slot dans les valeurs autorisées

Checks visuels (affichés, non bloquants) :
  - Titre de chaque jour → zone + thème lisibles
  - Types d'activités par jour → vérifier la rotation
  - Restaurants par jour → vérifier la diversité cuisine

Scénarios :
  1. Hammamet 3 jours — famille — été
  2. Tunis 1 jour    — solo   — exploration
  3. Djerba 2 jours  — couple — romantique

Usage :
    python -m app.test_day_planner
"""

import io
import json
import sys
import time
import traceback
import uuid

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from app.graph.builder import build_graph
from app.graph.state import build_initial_state

NATIVE_USER_ID = "99999999-0000-0000-0000-000000000000"

SCENARIOS = [
    {
        "id": 1,
        "name": "Hammamet 3 jours — famille",
        "message": "prépare moi un planning pour 3 jours à Hammamet avec ma femme et mes 2 enfants",
        "expected_days": 3,
    },
    {
        "id": 2,
        "name": "Tunis 1 jour — solo exploration",
        "message": "je veux un programme pour une journée à Tunis, je voyage seul",
        "expected_days": 1,
    },
    {
        "id": 3,
        "name": "Djerba 2 jours — couple romantique",
        "message": "programme de 2 jours à Djerba en amoureux, budget moyen",
        "expected_days": 2,
    },
]

VALID_TIME_SLOTS = {"morning", "afternoon", "evening"}
VALID_ITEM_TYPES = {"hotel", "restaurant", "activity", "flight", "free"}


# ─── Checks automatiques ─────────────────────────────────────────────────────

def check_itinerary(result: dict, expected_days: int) -> list:
    """Retourne une liste de (ok, message)."""
    checks = []

    # 1. itinerary généré
    itinerary = result.get("itinerary")
    if not itinerary:
        checks.append((False, "itinerary est None — day_planner n'a pas produit de résultat"))
        return checks
    checks.append((True, "itinerary généré"))

    days = itinerary.get("days") or []

    # 2. nombre de jours
    n_days = len(days)
    ok = (n_days == expected_days)
    checks.append((ok, f"duration_days: attendu={expected_days}, obtenu={n_days}"))

    # 3. candidate_id uniques entre les jours
    seen_ids = []
    dup_ids = []
    for day in days:
        for slot in day.get("slots") or []:
            cid = slot.get("candidate_id")
            if cid and cid != "null":
                if cid in seen_ids:
                    dup_ids.append(cid)
                else:
                    seen_ids.append(cid)
    if dup_ids:
        checks.append((False, f"candidate_id dupliqués entre jours : {dup_ids}"))
    else:
        checks.append((True, f"candidate_ids uniques ({len(seen_ids)} candidats réels utilisés)"))

    # 4. titres uniques
    titles = [day.get("title") for day in days if day.get("title")]
    dup_titles = [t for t in titles if titles.count(t) > 1]
    if dup_titles:
        checks.append((False, f"Titres dupliqués : {list(set(dup_titles))}"))
    else:
        checks.append((True, f"Titres uniques : {titles}"))

    # 5. time_slots valides
    invalid_slots = []
    for day in days:
        for slot in day.get("slots") or []:
            ts = slot.get("time_slot")
            if ts and ts not in VALID_TIME_SLOTS:
                invalid_slots.append(f"Jour {day.get('day_number')} → '{ts}'")
    if invalid_slots:
        checks.append((False, f"time_slots invalides : {invalid_slots}"))
    else:
        checks.append((True, "Tous les time_slots sont valides (morning/afternoon/evening)"))

    return checks


# ─── Affichage itinéraire ─────────────────────────────────────────────────────

def print_itinerary(itinerary: dict):
    if not itinerary:
        print("   (aucun itinéraire)")
        return

    days = itinerary.get("days") or []
    print(f"\n   destination  : {itinerary.get('destination')}")
    print(f"   duration_days: {itinerary.get('duration_days')}")
    print(f"   confidence   : {itinerary.get('confidence')}")

    for day in days:
        print(f"\n   ── Jour {day.get('day_number')} : {day.get('title')}")
        if day.get("day_notes"):
            print(f"      notes : {day['day_notes'][:100]}")
        for slot in day.get("slots") or []:
            ts   = slot.get("time_slot", "?")
            itype = slot.get("item_type", "?")
            name  = slot.get("name", "?")
            loc   = slot.get("location", "")
            cid   = slot.get("candidate_id") or "FREE"
            score = slot.get("ranked_score")
            score_str = f" [{score:.2f}]" if isinstance(score, (int, float)) else ""
            print(f"      [{ts:<10}] {itype:<12} {name:<35} {loc or '':<25} id={cid}{score_str}")

    if itinerary.get("weather_note"):
        print(f"\n   weather_note : {itinerary['weather_note'][:100]}")
    if itinerary.get("budget_note"):
        print(f"   budget_note  : {itinerary['budget_note'][:100]}")
    tips = itinerary.get("travel_tips") or []
    for i, tip in enumerate(tips, 1):
        print(f"   tip {i}        : {tip[:100]}")


# ─── Runner ───────────────────────────────────────────────────────────────────

def run_scenario(graph, scenario: dict) -> dict:
    state = build_initial_state(
        user_message    = scenario["message"],
        user_id         = NATIVE_USER_ID,
        session_id      = str(uuid.uuid4()),
        conversation_id = str(uuid.uuid4()),
    )

    start  = time.time()
    result = graph.invoke(state)
    elapsed = round(time.time() - start, 2)

    checks = check_itinerary(result, scenario["expected_days"])

    return {
        "id"           : scenario["id"],
        "name"         : scenario["name"],
        "elapsed"      : elapsed,
        "checks"       : checks,
        "intent"       : (result.get("intent_result") or {}).get("primary_intent", "—"),
        "suggestion_mode": result.get("suggestion_mode", "—"),
        "candidates"   : len(result.get("candidates") or []),
        "ranked"       : len(result.get("ranked_results") or []),
        "itinerary"    : result.get("itinerary"),
        "final_answer" : (result.get("final_answer") or "")[:300],
        "errors"       : result.get("errors") or [],
    }


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    print("=" * 70)
    print("  ZenifyTrip — Test Day Planner V2")
    print("=" * 70)

    print("\n[BUILD] Compilation du graphe...")
    try:
        graph = build_graph()
        print("[BUILD] OK\n")
    except Exception as e:
        print(f"[BUILD] FAIL : {e}")
        traceback.print_exc()
        return

    total_ok = 0
    total_ko = 0

    for sc in SCENARIOS:
        sep = "-" * max(0, 50 - len(sc["name"]))
        print(f"\n{'=' * 70}")
        print(f"  Scénario {sc['id']} : {sc['name']} {sep}")
        print(f"  Message  : \"{sc['message']}\"")
        print(f"  Attendu  : {sc['expected_days']} jour(s)")
        print(f"{'=' * 70}")

        try:
            r = run_scenario(graph, sc)
        except Exception as e:
            print(f"\n  [CRASH] {e}")
            traceback.print_exc()
            total_ko += 1
            continue

        passed = [c for c in r["checks"] if c[0]]
        failed = [c for c in r["checks"] if not c[0]]
        sc_ok  = len(failed) == 0

        if sc_ok:
            total_ok += 1
        else:
            total_ko += 1

        status = "[PASS]" if sc_ok else "[FAIL]"
        print(f"\n  {status}  |  {r['elapsed']}s  |  intent={r['intent']}  |  mode={r['suggestion_mode']}")
        print(f"  candidates={r['candidates']}  |  ranked={r['ranked']}  |  itinerary={bool(r['itinerary'])}")

        print(f"\n  Checks automatiques :")
        for ok, msg in r["checks"]:
            mark = "+" if ok else "X"
            print(f"    {mark} {msg}")

        print(f"\n  Itinéraire produit :")
        print_itinerary(r["itinerary"])

        if r["final_answer"]:
            print(f"\n  Réponse finale (extrait) :")
            print(f"  {r['final_answer'][:250]}")

        if r["errors"]:
            print(f"\n  Erreurs pipeline ({len(r['errors'])}) :")
            for err in r["errors"][:3]:
                print(f"    - {str(err)[:120]}")

    print(f"\n{'=' * 70}")
    print(f"  RÉSUMÉ : {total_ok}/{len(SCENARIOS)} PASS  |  {total_ko} FAIL")
    print(f"{'=' * 70}\n")


if __name__ == "__main__":
    main()
