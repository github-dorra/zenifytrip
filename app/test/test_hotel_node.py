import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from app.nodes.recommendation.domain.hotel_node import HotelNode

REQUIRED_FIELDS = [
    "id", "name", "stars", "zone_name", "address",
    "short_description", "long_description", "services",
    "coordinates", "is_partner", "score", "business_score", "user_score",
]

SCENARIOS = [
    {
        "name": "1 - USER NATIF | Monastir | Medium |   beach",
        "expect_empty": False,
        "current_hotel_id": None,
        "state": {
            "user_type": "native",
            "suggestion_mode": "precise_plan",
            "global_keywords": ["beachResort", "friendlyBudget"],
            "merged_context": {
                "destination": "monastir",
                "budget_level": "medium",
                "is_family": True,
            },
            "profile_data": {},
        },
    },
    
   
    
]


def validate(result: dict, scenario: dict) -> list:
    errors = []

    # --- clé hotel_candidates présente ---
    if "hotel_candidates" not in result:
        errors.append("clé 'hotel_candidates' manquante dans le retour")
        return errors

    candidates = result["hotel_candidates"]

    if not isinstance(candidates, list):
        errors.append(f"hotel_candidates n'est pas une liste : {type(candidates)}")
        return errors

    if scenario["expect_empty"]:
        if candidates:
            errors.append(f"résultat vide attendu mais {len(candidates)} candidats retournés")
        return errors

    # --- max 5 candidats ---
    if len(candidates) > 5:
        errors.append(f"trop de candidats : {len(candidates)} (max 5)")

    # --- au moins 1 résultat ---
    if len(candidates) == 0:
        errors.append("aucun candidat retourné (API injoignable ou filtre trop strict ?)")
        return errors

    # --- tri décroissant par score ---
    scores = [c["score"] for c in candidates]
    if scores != sorted(scores, reverse=True):
        errors.append(f"candidats non triés par score décroissant : {scores}")

    for i, c in enumerate(candidates):

        prefix = f"candidat[{i}]"

        # --- champs obligatoires ---
        for field in REQUIRED_FIELDS:
            if field not in c:
                errors.append(f"{prefix} champ manquant : '{field}'")

        # --- types de base ---
        if not isinstance(c.get("id", ""), str) or not c.get("id"):
            errors.append(f"{prefix} 'id' invalide : {c.get('id')!r}")

        if not isinstance(c.get("name", ""), str) or not c.get("name"):
            errors.append(f"{prefix} 'name' invalide : {c.get('name')!r}")

        stars = c.get("stars", -1)
        if not isinstance(stars, int) or stars < 0:
            errors.append(f"{prefix} 'stars' invalide : {stars!r}")

        # --- scores entre 0 et 1 ---
        for score_key in ("score", "business_score", "user_score"):
            v = c.get(score_key)
            if v is None or not (0.0 <= v <= 1.0):
                errors.append(f"{prefix} '{score_key}' hors intervalle [0,1] : {v}")

        # --- cohérence score final ---
        expected = round(0.7 * c.get("user_score", 0) + 0.3 * c.get("business_score", 0), 4)
        if abs(c.get("score", 0) - expected) > 0.001:
            errors.append(
                f"{prefix} score incohérent : score={c.get('score')} "
                f"attendu={expected} (0.7*{c.get('user_score')} + 0.3*{c.get('business_score')})"
            )

        # --- is_partner cohérent avec services ---
        services = c.get("services", [])
        is_partner = c.get("is_partner", False)
        if is_partner and not services:
            errors.append(f"{prefix} is_partner=True mais services vide")
        if not is_partner and services:
            errors.append(f"{prefix} is_partner=False mais services non vide : {services}")

        # --- USER RÉEL : hôtel actuel non présent ---
        if scenario["current_hotel_id"] and c.get("id") == scenario["current_hotel_id"]:
            errors.append(f"{prefix} hôtel actuel du voyageur ne doit pas apparaître")

    return errors


def run():
    node = HotelNode()
    total_pass = 0
    total_fail = 0

    for scenario in SCENARIOS:
        print(f"\n{'='*65}")
        print(f"SCENARIO {scenario['name']}")
        print("="*65)

        result = node.run(scenario["state"])
        candidates = result.get("hotel_candidates", [])

        print(f"  candidats retournés : {len(candidates)}")
        for c in candidates:
            print(
                f"    [{c.get('stars', '?')}★] {c.get('name', '?'):<45} "
                f"score={c.get('score', 0):.3f} "
                f"partner={'✓' if c.get('is_partner') else '✗'} "
                f"services={c.get('services', [])}"
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

    print(f"\n{'='*65}")
    print(f"RESULTATS : {total_pass} PASS / {total_fail} FAIL sur {len(SCENARIOS)} scénarios")
    print("="*65)


if __name__ == "__main__":
    run()
