"""
Test orchestrateur intelligent — 4 scénarios ciblés.
Usage : python -m app.test_orchestrator
"""
import io
import sys
import json

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from app.nodes.recommendation.orchestration.orchestrator_node import OrchestratorNode

PASS = "\033[92m✅ PASS\033[0m"
FAIL = "\033[91m❌ FAIL\033[0m"

node = OrchestratorNode()
results = []


def check(result: dict, label: str, expected):
    actual = expected(result) if callable(expected) else expected
    ok = actual if isinstance(actual, bool) else (actual == expected)
    # If expected is callable, actual IS the check result
    ok = actual if callable(expected) else (actual == expected)
    print(f"    {'✅' if ok else '❌'}  {label}")
    return ok


def run_scenario(name: str, state: dict, checks_fn):
    print(f"\n{'─'*60}")
    print(f"  {name}")
    print(f"{'─'*60}")
    result = node.run(state)
    services = result.get("requested_services") or []
    reasoning = result.get("orchestrator_reasoning") or ""
    cts = result.get("orchestrator_constraints") or {}
    path = "rules" if reasoning.startswith("rules:") else "LLM"

    print(f"  path        : {path}")
    print(f"  services    : {services}")
    print(f"  reasoning   : {reasoning[:140]}")
    for svc, c in cts.items():
        print(f"  [{svc}] : {json.dumps(c, ensure_ascii=False)}")

    all_pass = checks_fn(result)
    results.append((name, all_pass))
    return result


# ══════════════════════════════════════════════════════════════════════════════
# SCÉNARIO 1 — USER RÉEL, HB, DERNIER JOUR, départ 14h
# ══════════════════════════════════════════════════════════════════════════════
state_s1 = {
    "intent_result": {
        "primary_intent": "day_planning",
        "secondary_intents": [],
        "action_type": "recommendation",
        "language": "fr",
    },
    "suggestion_mode": "precise_plan",
    "user_type": "real",
    "merged_context": {
        "destination": "djerba",
        "origin": None,
        "budget_level": "medium",
        "interests": ["culture"],
        "rejected_types": [],
        "liked_types": [],
    },
    "availability_result": {
        "trip_is_ongoing": True,
        "outbound_date":   "2026-07-25",
        "return_date":     "2026-07-31",
        "days_remaining":  0,
        "hotel_name":      "Djerba Plaza",
        "destination":     "djerba",
    },
    "trip_position": {
        "day_index":       7,
        "total_days":      7,
        "is_first_day":    False,
        "is_last_day":     True,
        "arrival_time":    None,
        "departure_time":  "14:00",
    },
    "booking_anchors": {
        "meal_plan":           "HB",
        "breakfast_included":  True,
        "lunch_included":      False,
        "dinner_included":     True,
        "hotel_name":          "Djerba Plaza",
        "booked_services":     [],
    },
    "day_skeleton": {
        "destination": "djerba",
        "duration_days": 1,
        "day_context": {"is_last_day": True},
        "days": [{
            "day_number": 1,
            "date": "2026-07-31",
            "mode": "morning_only_departure",
            "slots": [
                {"time_slot": "breakfast", "status": "anchored",
                 "item_type": "meal_included", "name": "Petit-déjeuner inclus à l'hôtel"},
                {"time_slot": "morning",   "status": "open", "item_type": None, "name": None},
                {"time_slot": "logistics", "status": "anchored",
                 "item_type": "logistics",  "name": "Check-out + transfert aéroport"},
            ],
        }],
    },
    "orchestrator_constraints": None,
    "orchestrator_reasoning":   None,
    "global_keywords": ["culturalActivity"],
    "contextual_keywords": [],
    "weather_context": None,
    "profile_data": {},
    "travellerId": "trav-001",
}

def checks_s1(r):
    svcs = r.get("requested_services") or []
    cts  = r.get("orchestrator_constraints") or {}
    orch_act = cts.get("activity_node") or {}
    all_ok = True
    tests = [
        ("chemin LLM (trip_is_ongoing + is_last_day + HB + anchors)",
            not (r.get("orchestrator_reasoning") or "").startswith("rules:")),
        ("hotel_node ABSENT (trip_is_ongoing=True)",
            "hotel_node" not in svcs),
        ("flight_node ABSENT (trip_is_ongoing=True)",
            "flight_node" not in svcs),
        ("activity_node PRÉSENT (1 slot morning ouvert)",
            "activity_node" in svcs),
        ("restaurant_node ABSENT (morning_only_departure : breakfast anchored, départ 14h, pas de slot déj)",
            "restaurant_node" not in svcs),
        ("constraints activity_node injectées",
            bool(orch_act)),
        ("max_duration_hours injecté (dernière matinée)",
            orch_act.get("max_duration_hours") is not None),
    ]
    for label, ok in tests:
        print(f"    {'✅' if ok else '❌'}  {label}")
        if not ok:
            all_ok = False
    return all_ok

run_scenario("S1 — USER RÉEL HB dernier jour (dép 14h)", state_s1, checks_s1)


# ══════════════════════════════════════════════════════════════════════════════
# SCÉNARIO 2 — USER RÉEL, AI jour normal, activity_recommendation
# ══════════════════════════════════════════════════════════════════════════════
state_s2 = {
    "intent_result": {
        "primary_intent": "activity_recommendation",
        "secondary_intents": [],
        "action_type": "recommendation",
        "language": "fr",
    },
    "suggestion_mode": "precise_plan",
    "user_type": "real",
    "merged_context": {
        "destination": "sousse",
        "origin": None,
        "budget_level": "medium",
        "interests": ["culture"],
        "rejected_types": [],
        "liked_types": [],
    },
    "availability_result": {"trip_is_ongoing": True, "days_remaining": 3},
    "trip_position": {
        "is_last_day": False, "is_first_day": False,
        "day_index": 3, "total_days": 5,
        "arrival_time": None, "departure_time": None,
    },
    "booking_anchors": {
        "meal_plan":          "AI",
        "breakfast_included": True,
        "lunch_included":     True,
        "dinner_included":    True,
        "booked_services":    [],
    },
    "day_skeleton": None,
    "orchestrator_constraints": None,
    "orchestrator_reasoning":   None,
    "global_keywords": ["culturalActivity"],
    "contextual_keywords": [],
    "weather_context": None,
    "profile_data": {},
    "travellerId": "trav-001",
}

def checks_s2(r):
    svcs = r.get("requested_services") or []
    all_ok = True
    tests = [
        ("chemin LLM (AI + trip_is_ongoing)",
            not (r.get("orchestrator_reasoning") or "").startswith("rules:")),
        ("hotel_node ABSENT (trip_is_ongoing=True)", "hotel_node" not in svcs),
        ("flight_node ABSENT (trip_is_ongoing=True)", "flight_node" not in svcs),
        ("activity_node PRÉSENT", "activity_node" in svcs),
        ("restaurant_node ABSENT (AI = tout inclus, pas d'intent resto)",
            "restaurant_node" not in svcs),
    ]
    for label, ok in tests:
        print(f"    {'✅' if ok else '❌'}  {label}")
        if not ok:
            all_ok = False
    return all_ok

run_scenario("S2 — USER RÉEL AI jour normal (activity_recommendation)", state_s2, checks_s2)


# ══════════════════════════════════════════════════════════════════════════════
# SCÉNARIO 3 — USER NATIF, pas de voyage, day_planning → chemin RÈGLES
# ══════════════════════════════════════════════════════════════════════════════
state_s3 = {
    "intent_result": {
        "primary_intent": "day_planning",
        "secondary_intents": [],
        "action_type": "recommendation",
        "language": "fr",
    },
    "suggestion_mode": "exploratory",
    "user_type": "native",
    "merged_context": {
        "destination": "hammamet",
        "origin": None,
        "budget_level": "medium",
        "interests": [],
        "rejected_types": [],
        "liked_types": [],
    },
    "availability_result": {"trip_is_ongoing": False},
    "trip_position": {"is_last_day": False, "is_first_day": False},
    "booking_anchors": {"meal_plan": None},
    "day_skeleton": None,
    "orchestrator_constraints": None,
    "orchestrator_reasoning":   None,
    "global_keywords": [],
    "contextual_keywords": [],
    "weather_context": None,
    "profile_data": {},
    "travellerId": None,
}

def checks_s3(r):
    svcs = r.get("requested_services") or []
    reasoning = r.get("orchestrator_reasoning") or ""
    all_ok = True
    tests = [
        ("chemin RÈGLES (0 LLM)", reasoning.startswith("rules:")),
        ("hotel_node présent",      "hotel_node"      in svcs),
        ("activity_node présent",   "activity_node"   in svcs),
        ("restaurant_node présent", "restaurant_node" in svcs),
        ("flight_node absent",      "flight_node"     not in svcs),
    ]
    for label, ok in tests:
        print(f"    {'✅' if ok else '❌'}  {label}")
        if not ok:
            all_ok = False
    return all_ok

run_scenario("S3 — USER NATIF day_planning (chemin règles)", state_s3, checks_s3)


# ══════════════════════════════════════════════════════════════════════════════
# SCÉNARIO 4 — USER RÉEL, AI, veut un restaurant EXPLICITEMENT
# ══════════════════════════════════════════════════════════════════════════════
state_s4 = {
    "intent_result": {
        "primary_intent": "restaurant_recommendation",
        "secondary_intents": [],
        "action_type": "recommendation",
        "language": "fr",
    },
    "suggestion_mode": "precise_plan",
    "user_type": "real",
    "merged_context": {
        "destination": "djerba",
        "origin": None,
        "budget_level": "luxury",
        "interests": [],
        "rejected_types": [],
        "liked_types": [],
        "restaurant_preferences": [],
    },
    "availability_result": {"trip_is_ongoing": True, "days_remaining": 2},
    "trip_position": {
        "is_last_day": False, "is_first_day": False,
        "day_index": 3, "total_days": 5,
        "arrival_time": None, "departure_time": None,
    },
    "booking_anchors": {
        "meal_plan":          "AI",
        "breakfast_included": True,
        "lunch_included":     True,
        "dinner_included":    True,
        "booked_services":    [],
    },
    "day_skeleton": None,
    "orchestrator_constraints": None,
    "orchestrator_reasoning":   None,
    "global_keywords": ["romanticDining"],
    "contextual_keywords": [],
    "weather_context": None,
    "profile_data": {},
    "travellerId": "trav-001",
}

def checks_s4(r):
    svcs = r.get("requested_services") or []
    cts  = r.get("orchestrator_constraints") or {}
    resto_cts = cts.get("restaurant_node") or {}
    all_ok = True
    tests = [
        ("restaurant_node PRÉSENT (intent explicite override AI)",
            "restaurant_node" in svcs),
        ("optional_experience=True injecté",
            bool(resto_cts.get("optional_experience"))),
        ("hotel_node ABSENT", "hotel_node" not in svcs),
        ("flight_node ABSENT", "flight_node" not in svcs),
    ]
    for label, ok in tests:
        print(f"    {'✅' if ok else '❌'}  {label}")
        if not ok:
            all_ok = False
    return all_ok

run_scenario("S4 — USER RÉEL AI + restaurant explicite (optional_experience)", state_s4, checks_s4)


# ══════════════════════════════════════════════════════════════════════════════
print(f"\n{'═'*60}")
total  = len(results)
passed = sum(1 for _, ok in results if ok)
print(f"  RÉSULTAT : {passed}/{total} scénarios PASS")
for name, ok in results:
    print(f"    {'✅' if ok else '❌'}  {name}")
print(f"{'═'*60}\n")
