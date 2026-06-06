import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from app.nodes.recommendation.domain.flight_node import FlightNode

REQUIRED_FIELDS = [
    "id", "flight_type", "has_layover", "layover_count",
    "match_score", "matched_criteria", "tier",
]

# Profil simulé USER RÉEL avec vols aller/retour
PROFILE_REAL = {
    "outboundFlight": {
        "flightNumber": "TU101",
        "takeoffTime": "2026-07-01T07:00:00",
        "landingTime": "2026-07-01T09:30:00",
        "airTime": 150,
        "takeoffAirport": {"name": "Paris Charles de Gaulle", "iataCode": "CDG"},
        "landingAirport": {"name": "Tunis-Carthage", "iataCode": "TUN"},
    },
    "returnFlight": {
        "flightNumber": "TU202",
        "takeoffTime": "2026-07-15T14:00:00",
        "landingTime": "2026-07-15T16:30:00",
        "airTime": 150,
        "takeoffAirport": {"name": "Tunis-Carthage", "iataCode": "TUN"},
        "landingAirport": {"name": "Paris Charles de Gaulle", "iataCode": "CDG"},
    },
}

SCENARIOS = [
    {
        "name": "1 - USER NATIF | destination=tunis | Tier 2 catalogue",
        "expect_empty": False,
        "expect_tier1": False,
        "state": {
            "user_type": "native",
            "suggestion_mode": "precise_plan",
            "profile_data": {},
            "merged_context": {
                "constraints": {
                    "destination": "tunis",
                    "origin": None,
                    "flight_preferences": {},
                },
            },
        },
    },
    {
        "name": "2 - USER NATIF | exploratory | pas de destination",
        "expect_empty": False,
        "expect_tier1": False,
        "state": {
            "user_type": "native",
            "suggestion_mode": "exploratory",
            "profile_data": {},
            "merged_context": {
                "constraints": {
                    "destination": None,
                    "origin": None,
                    "flight_preferences": {},
                },
            },
        },
    },
    {
        "name": "3 - USER RÉEL | profil avec vols tunis | Tier 1 profil",
        "expect_empty": False,
        "expect_tier1": True,
        "state": {
            "user_type": "real",
            "suggestion_mode": "precise_plan",
            "profile_data": PROFILE_REAL,
            "merged_context": {
                "constraints": {
                    "destination": "tunis",
                    "origin": None,
                    "flight_preferences": {},
                },
            },
        },
    },
    {
        "name": "4 - USER RÉEL | profil tunis mais demande paris | Tier 1 ne matche → Tier 2",
        "expect_empty": False,
        "expect_tier1": False,
        "state": {
            "user_type": "real",
            "suggestion_mode": "semi_exploratory",
            "profile_data": PROFILE_REAL,
            "merged_context": {
                "constraints": {
                    "destination": "paris",
                    "origin": None,
                    "flight_preferences": {},
                },
            },
        },
    },
    {
        "name": "5 - USER NATIF | préférence vol direct",
        "expect_empty": False,
        "expect_tier1": False,
        "state": {
            "user_type": "native",
            "suggestion_mode": "precise_plan",
            "profile_data": {},
            "merged_context": {
                "constraints": {
                    "destination": None,
                    "origin": None,
                    "flight_preferences": {"flight_type": "direct"},
                },
            },
        },
    },
    {
        "name": "6 - USER RÉEL | profil sans vols → fallback Tier 2",
        "expect_empty": False,
        "expect_tier1": False,
        "state": {
            "user_type": "real",
            "suggestion_mode": "precise_plan",
            "profile_data": {},
            "merged_context": {
                "constraints": {
                    "destination": "tunis",
                    "origin": None,
                    "flight_preferences": {},
                },
            },
        },
    },
]


def validate(result: dict, scenario: dict) -> list:
    errors = []

    # --- clé flight_candidates présente ---
    if "flight_candidates" not in result:
        errors.append("clé 'flight_candidates' manquante dans le retour")
        return errors

    candidates = result["flight_candidates"]

    if not isinstance(candidates, list):
        errors.append(f"flight_candidates n'est pas une liste : {type(candidates)}")
        return errors

    if scenario["expect_empty"]:
        if candidates:
            errors.append(f"résultat vide attendu mais {len(candidates)} candidats retournés")
        return errors

    if len(candidates) == 0:
        errors.append("aucun candidat retourné (API injoignable ou filtre trop strict ?)")
        return errors

    # --- tri décroissant par match_score ---
    scores = [c.get("match_score", 0) for c in candidates]
    if scores != sorted(scores, reverse=True):
        errors.append(f"candidats non triés par match_score décroissant : {scores}")

    # --- Tier 1 attendu ---
    if scenario["expect_tier1"]:
        tier1 = [c for c in candidates if c.get("tier") == "profile"]
        if not tier1:
            errors.append("Tier 1 (profile) attendu mais aucun candidat tier='profile'")
        else:
            for c in tier1:
                if c.get("match_score") != 1.0:
                    errors.append(f"Tier 1 match_score doit être 1.0, reçu : {c.get('match_score')}")

    for i, c in enumerate(candidates):
        prefix = f"candidat[{i}]"

        # --- champs obligatoires ---
        for field in REQUIRED_FIELDS:
            if field not in c:
                errors.append(f"{prefix} champ manquant : '{field}'")

        # --- id non vide ---
        if not c.get("id"):
            errors.append(f"{prefix} 'id' vide ou absent")

        # --- match_score entre 0 et 1 ---
        score = c.get("match_score")
        if score is None or not (0.0 <= score <= 1.0):
            errors.append(f"{prefix} 'match_score' hors intervalle [0,1] : {score}")

        # --- has_layover est bool ---
        if not isinstance(c.get("has_layover"), bool):
            errors.append(f"{prefix} 'has_layover' doit être bool : {c.get('has_layover')!r}")

        # --- layover_count est int >= 0 ---
        lc = c.get("layover_count")
        if not isinstance(lc, int) or lc < 0:
            errors.append(f"{prefix} 'layover_count' invalide : {lc!r}")

        # --- matched_criteria est une liste ---
        if not isinstance(c.get("matched_criteria"), list):
            errors.append(f"{prefix} 'matched_criteria' doit être une liste")

        # --- tier valide ---
        tier = c.get("tier")
        if tier not in ("profile", "catalogue"):
            errors.append(f"{prefix} 'tier' invalide : {tier!r} (attendu 'profile' ou 'catalogue')")

        # --- duration_hours cohérent avec duration_minutes ---
        dm = c.get("duration_minutes")
        dh = c.get("duration_hours")
        if dm and dh:
            expected_h = round(dm / 60, 2)
            if abs(dh - expected_h) > 0.05:
                errors.append(f"{prefix} duration_hours={dh} incohérent avec duration_minutes={dm} (attendu ~{expected_h})")

    return errors


def run():
    node = FlightNode()
    total_pass = 0
    total_fail = 0

    for scenario in SCENARIOS:
        print(f"\n{'='*70}")
        print(f"SCENARIO {scenario['name']}")
        print("=" * 70)

        result = node.run(scenario["state"])
        candidates = result.get("flight_candidates", [])

        tier1 = [c for c in candidates if c.get("tier") == "profile"]
        tier2 = [c for c in candidates if c.get("tier") == "catalogue"]

        print(f"  candidats : {len(candidates)} total (tier1_profile={len(tier1)}, tier2_catalogue={len(tier2)})")

        for c in candidates:
            takeoff = (c.get("takeoff_airport") or {}).get("iata_code") or "?"
            landing = (c.get("landing_airport") or {}).get("iata_code") or "?"
            airline = (c.get("airline") or {}).get("name") or "?"
            print(
                f"    [{c.get('tier','?'):9}] {takeoff}→{landing:<6} "
                f"n°{c.get('flight_number') or '?':<10} "
                f"{c.get('flight_type','?'):12} "
                f"dur={c.get('duration_hours','?')}h "
                f"score={c.get('match_score',0):.3f} "
                f"compagnie={airline}"
            )

        errors = validate(result, scenario)

        if errors:
            total_fail += 1
            print(f"  [FAIL] {len(errors)} erreur(s) :")
            for e in errors:
                print(f"    - {e}")
        else:
            total_pass += 1
            print(f"  [PASS]")

    print(f"\n{'='*70}")
    print(f"RESULTATS : {total_pass} PASS / {total_fail} FAIL sur {len(SCENARIOS)} scénarios")
    print("=" * 70)


if __name__ == "__main__":
    run()
