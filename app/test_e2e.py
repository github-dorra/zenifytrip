"""
Test end-to-end ZenifyTrip — Pipeline complet Phase 1→4.

Scénarios :
  1. Greeting                        → Agent 1 (final_response)
  2. Question générale               → Agent 1
  3. Clarification (manque destination) → Agent 1
  4. Activity USER NATIF Djerba      → Agent 2 (recommendation_response)
  5. Restaurant Sousse halal         → Agent 2
  6. Day planning Hammamet 3j        → Agent 2 + day_planner
  7. Hôtel recommendation            → Agent 2
  8. USER RÉEL activités (profil API)→ Agent 2 avec profil enrichi

Usage :
    python -m app.test_e2e
"""

import io
import json
import sys
import time
import traceback
import uuid
from typing import Any, Callable, Dict, List, Tuple, Union

# Force UTF-8 sur Windows (terminal CP1252 par defaut)
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from app.graph.builder import build_graph
from app.graph.state import build_initial_state

# ── IDs ──────────────────────────────────────────────────────────────────────
REAL_USER_ID   = "df55d964-039d-4838-8e5e-352ce1708bd9"
NATIVE_USER_ID = "99999999-0000-0000-0000-000000000000"   # inexistant → USER NATIF

# ── Helpers d'assertion ───────────────────────────────────────────────────────
def _check(result: Dict, kind: str, field: str, expected: Any) -> Tuple[bool, str]:
    """
    Retourne (ok: bool, detail: str).
    kind : "intent" | "state" | "errors" | "candidates"
    """
    try:
        if kind == "intent":
            actual = (result.get("intent_result") or {}).get(field)
        elif kind == "state":
            actual = result.get(field)
        elif kind == "errors":
            actual = len(result.get("errors") or [])
            expected_val = expected
            if actual != expected_val:
                err_details = json.dumps(result.get("errors") or [], ensure_ascii=False)
                return False, f"errors: attendu {expected_val}, obtenu {actual} — {err_details[:300]}"
            return True, f"errors: {actual}"
        elif kind == "candidates":
            actual = len(result.get(field) or [])
        else:
            return False, f"kind inconnu: {kind}"

        if callable(expected):
            ok = expected(actual)
            return ok, f"{kind}.{field} = {repr(actual)[:80]}"
        else:
            ok = (actual == expected)
            return ok, f"{kind}.{field}: attendu={repr(expected)}, obtenu={repr(actual)[:80]}"

    except Exception as e:
        return False, f"EXCEPTION dans check {kind}.{field}: {e}"


# ── Définition des scénarios ──────────────────────────────────────────────────
SCENARIOS = [
    {
        "id"     : 1,
        "name"   : "Greeting",
        "user_id": NATIVE_USER_ID,
        "message": "Bonjour",
        "checks" : [
            ("intent", "primary_intent", "greeting"),
            ("state",  "user_type",      "native"),
            ("state",  "final_answer",   lambda v: bool(v)),
            ("errors", None,             0),
        ],
    },
    {
        "id"     : 2,
        "name"   : "Question générale (travel_question)",
        "user_id": NATIVE_USER_ID,
        "message": "Quels sont les meilleurs endroits à visiter en Tunisie ?",
        "checks" : [
            ("state",  "final_answer", lambda v: bool(v)),
            ("errors", None,           0),
        ],
    },
    {
        "id"     : 3,
        "name"   : "Clarification — destination manquante",
        "user_id": NATIVE_USER_ID,
        "message": "je veux faire des activités",
        "checks" : [
            ("intent", "primary_intent",        "activity_recommendation"),
            ("state",  "clarification_needed",  True),
            ("state",  "clarification_question", lambda v: bool(v)),
            ("state",  "final_answer",           lambda v: bool(v)),
            ("errors", None,                     0),
        ],
    },
    {
        "id"     : 4,
        "name"   : "Activity — USER NATIF Djerba",
        "user_id": NATIVE_USER_ID,
        "message": "je veux faire des activités culturelles à Djerba",
        "checks" : [
            ("intent",      "primary_intent",  "activity_recommendation"),
            ("state",       "user_type",        "native"),
            ("state",       "final_answer",     lambda v: bool(v)),
            ("errors",      None,               0),
        ],
    },
    {
        "id"     : 5,
        "name"   : "Restaurant — Sousse halal",
        "user_id": NATIVE_USER_ID,
        "message": "recommande moi un restaurant halal à Sousse pour ce soir",
        "checks" : [
            ("intent", "primary_intent", "restaurant_recommendation"),
            ("state",  "final_answer",   lambda v: bool(v)),
            ("errors", None,             0),
        ],
    },
    {
        "id"     : 6,
        "name"   : "Day planning — Hammamet 3 jours",
        "user_id": NATIVE_USER_ID,
        "message": "prépare moi un planning pour 3 jours à Hammamet avec famille",
        "checks" : [
            ("intent", "primary_intent", "day_planning"),
            ("state",  "final_answer",   lambda v: bool(v)),
            ("errors", None,             0),
        ],
    },
    {
        "id"     : 7,
        "name"   : "Hôtel — Tunis budget moyen",
        "user_id": NATIVE_USER_ID,
        "message": "je cherche un hôtel à Tunis pour 2 personnes budget moyen",
        "checks" : [
            ("intent", "primary_intent", "accommodation_recommendation"),
            ("state",  "final_answer",   lambda v: bool(v)),
            ("errors", None,             0),
        ],
    },
    {
        "id"     : 8,
        "name"   : "USER RÉEL — activités (profil API)",
        "user_id": REAL_USER_ID,
        "message": "je veux faire des activités aujourd'hui",
        "checks" : [
            ("state",  "user_type",    "real"),
            ("state",  "profile_data", lambda v: bool(v)),
            ("state",  "final_answer", lambda v: bool(v)),
            ("errors", None,           0),
        ],
    },
]


# ── Runner ────────────────────────────────────────────────────────────────────
def run_scenario(graph, scenario: Dict) -> Dict:
    state = build_initial_state(
        user_message    = scenario["message"],
        user_id         = scenario["user_id"],
        session_id      = str(uuid.uuid4()),
        conversation_id = str(uuid.uuid4()),
    )

    start  = time.time()
    result = graph.invoke(state)
    duration = round(time.time() - start, 2)

    checks = scenario.get("checks", [])
    passed = []
    failed = []

    for (kind, field, expected) in checks:
        ok, detail = _check(result, kind, field, expected)
        (passed if ok else failed).append(detail)

    return {
        "id"          : scenario["id"],
        "name"        : scenario["name"],
        "duration_s"  : duration,
        "passed"      : passed,
        "failed"      : failed,
        "intent"      : (result.get("intent_result") or {}).get("primary_intent", "—"),
        "next_action" : result.get("next_action", "—"),
        "user_type"   : result.get("user_type", "—"),
        "suggestion_mode": result.get("suggestion_mode", "—"),
        "candidates"  : len(result.get("candidates") or []),
        "ranked"      : len(result.get("ranked_results") or []),
        "has_itinerary": bool(result.get("itinerary")),
        "final_answer" : (result.get("final_answer") or "")[:200],
        "error_count" : len(result.get("errors") or []),
        "errors"      : result.get("errors") or [],
    }


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    print("=" * 70)
    print("  ZenifyTrip - Test End-to-End Pipeline")
    print("=" * 70)

    print("\n[BUILD] Compilation du graphe...")
    try:
        graph = build_graph()
        print("[BUILD] OK - Graphe compile\n")
    except Exception as e:
        print(f"[BUILD] FAIL - Echec compilation graphe : {e}")
        traceback.print_exc()
        return

    results  = []
    total_ok = 0
    total_ko = 0

    for scenario in SCENARIOS:
        sid  = scenario["id"]
        name = scenario["name"]
        sep  = "-" * max(0, 45 - len(name))
        print(f"-- Scenario {sid} : {name} {sep}")
        print(f"   Message : \"{scenario['message']}\"")

        try:
            r = run_scenario(graph, scenario)
        except Exception as e:
            print(f"   [CRASH] {e}")
            traceback.print_exc()
            results.append({"id": sid, "name": name, "failed": [str(e)], "passed": [], "duration_s": 0})
            total_ko += 1
            print()
            continue

        ok     = len(r["failed"]) == 0
        status = "[PASS]" if ok else "[FAIL]"
        if ok:
            total_ok += 1
        else:
            total_ko += 1

        print(f"   {status}  |  {r['duration_s']}s  |  intent={r['intent']}  |  user={r['user_type']}  |  mode={r['suggestion_mode']}")
        print(f"   next_action={r['next_action']}  |  candidates={r['candidates']}  |  ranked={r['ranked']}  |  itinerary={r['has_itinerary']}")

        for detail in r["passed"]:
            print(f"      + {detail}")
        for detail in r["failed"]:
            print(f"      X {detail}")

        if r["final_answer"]:
            ans = r["final_answer"][:150]
            tail = "..." if len(r["final_answer"]) >= 150 else ""
            print(f"   Answer : {ans}{tail}")

        if r["error_count"]:
            print(f"   Errors ({r['error_count']}) :")
            for err in r["errors"][:3]:
                msg = str(err)[:120]
                print(f"      - {msg}")
        print()
        results.append(r)

    # -- Resume ----------------------------------------------------------------
    print("=" * 70)
    print(f"  RESUME : {total_ok}/{len(SCENARIOS)} PASS  |  {total_ko} FAIL")
    print("=" * 70)

    checks_total  = sum(len(r["passed"]) + len(r["failed"]) for r in results)
    checks_passed = sum(len(r["passed"]) for r in results)
    avg_duration  = round(sum(r.get("duration_s", 0) for r in results) / max(len(results), 1), 2)

    print(f"  Assertions : {checks_passed}/{checks_total}")
    print(f"  Duree moy  : {avg_duration}s / scenario")

    if total_ko:
        print("\n  Scenarios en echec :")
        for r in results:
            if r["failed"]:
                print(f"    - Scenario {r['id']} : {r['name']}")
                for f in r["failed"]:
                    print(f"        X {f}")

    print()


if __name__ == "__main__":
    main()
