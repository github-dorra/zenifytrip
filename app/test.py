import re
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from app.nodes.recommendation.context.semantic_node import SemanticAgentNode

CAMEL_PATTERN = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9]*$")

SCENARIOS = [
    {
        "name": "1 - activity_recommendation (famille, plage, budget low, soleil)",
        "expect_fallback": False,
        "state": {
            "user_message": "recommande moi des activites a faire demain a Monastir",
            "merged_context": {
                "primary_intent": "activity_recommendation",
                "secondary_intents": [],
                "destination": "monastir",
                "travelers": 4,
                "is_family": True,
                "duration_days": 5,
                "budget_level": "low",
                "interests": ["beach", "water", "kids"],
            },
            "weather_context": {
                "insights": {
                    "avg_temperature": 31,
                    "is_hot_day": True,
                    "is_rainy_day": False,
                    "is_sunny_day": True,
                    "beach_score": 0.95,
                    "outdoor_score": 0.90,
                    "indoor_score": 0.20,
                    "recommendation_hint": "beach",
                }
            },
        },
    },
    {
        "name": "2 - accommodation_recommendation (couple luxe, Djerba, pluie)",
        "expect_fallback": False,
        "state": {
            "user_message": "je cherche un hotel romantique a Djerba pour 7 jours",
            "merged_context": {
                "primary_intent": "accommodation_recommendation",
                "secondary_intents": [],
                "destination": "djerba",
                "travelers": 2,
                "is_family": False,
                "duration_days": 7,
                "budget_level": "luxury",
                "interests": ["spa", "romance", "relax"],
            },
            "weather_context": {
                "insights": {
                    "avg_temperature": 18,
                    "is_hot_day": False,
                    "is_rainy_day": True,
                    "is_sunny_day": False,
                    "beach_score": 0.20,
                    "outdoor_score": 0.30,
                    "indoor_score": 0.90,
                    "recommendation_hint": "indoor",
                }
            },
        },
    },
    {
        "name": "3 - restaurant_recommendation (solo, street food, Sousse)",
        "expect_fallback": False,
        "state": {
            "user_message": "ou manger ce soir a Sousse, pas trop cher",
            "merged_context": {
                "primary_intent": "restaurant_recommendation",
                "secondary_intents": [],
                "destination": "sousse",
                "travelers": 1,
                "is_family": False,
                "duration_days": 3,
                "budget_level": "low",
                "interests": ["local food", "street food"],
            },
            "weather_context": {
                "insights": {
                    "avg_temperature": 24,
                    "is_hot_day": False,
                    "is_rainy_day": False,
                    "is_sunny_day": True,
                    "beach_score": 0.60,
                    "outdoor_score": 0.75,
                    "indoor_score": 0.40,
                    "recommendation_hint": "outdoor",
                }
            },
        },
    },
    {
        "name": "4 - flight_recommendation (business class, Tunis-Paris)",
        "expect_fallback": False,
        "state": {
            "user_message": "je veux un vol business class de Tunis a Paris demain matin",
            "merged_context": {
                "primary_intent": "flight_recommendation",
                "secondary_intents": [],
                "destination": "paris",
                "origin": "tunis",
                "travelers": 1,
                "is_family": False,
                "duration_days": 2,
                "budget_level": "luxury",
                "interests": [],
            },
            "weather_context": {"insights": {}},
        },
    },
    {
        "name": "5 - travel_question (sans destination, sans meteo)",
        "expect_fallback": False,
        "state": {
            "user_message": "quelle est la meilleure saison pour visiter la Tunisie ?",
            "merged_context": {
                "primary_intent": "travel_question",
                "secondary_intents": [],
                "destination": None,
                "travelers": None,
                "is_family": False,
                "duration_days": None,
                "budget_level": None,
                "interests": [],
            },
            "weather_context": {"insights": {}},
        },
    },
    {
        "name": "6 - merged_context vide (fallback attendu)",
        "expect_fallback": True,
        "state": {
            "user_message": "bonjour",
            "merged_context": {},
            "weather_context": {},
        },
    },
]


def validate(result: dict, scenario_name: str, expect_fallback: bool) -> list:
    errors = []

    semantic_query      = result.get("semantic_query")
    global_keywords     = result.get("global_keywords", [])
    contextual_keywords = result.get("contextual_keywords", [])
    semantic_metadata   = result.get("semantic_metadata", {})
    cache_key           = result.get("semantic_cache_key")

    # --- clés obligatoires présentes ---
    for key in ("semantic_query", "global_keywords", "contextual_keywords",
                "semantic_metadata", "semantic_cache_key"):
        if key not in result:
            errors.append(f"clé manquante : {key}")

    if expect_fallback:
        if semantic_query is not None:
            errors.append(f"fallback attendu mais semantic_query={semantic_query!r}")
        if global_keywords:
            errors.append(f"fallback attendu mais global_keywords non vide : {global_keywords}")
        return errors

    # --- semantic_query ---
    if semantic_query is None:
        errors.append("semantic_query est None (LLM a echoue)")
    elif len(semantic_query) > 50:
        errors.append(f"semantic_query trop long ({len(semantic_query)} chars) : {semantic_query!r}")

    # --- global_keywords ---
    if len(global_keywords) > 8:
        errors.append(f"global_keywords depasse 8 : {len(global_keywords)} items")
    for kw in global_keywords:
        if not CAMEL_PATTERN.match(kw):
            errors.append(f"global_keyword format invalide : {kw!r}")

    # --- contextual_keywords ---
    if len(contextual_keywords) > 8:
        errors.append(f"contextual_keywords depasse 8 : {len(contextual_keywords)} items")
    for kw in contextual_keywords:
        if not CAMEL_PATTERN.match(kw):
            errors.append(f"contextual_keyword format invalide : {kw!r}")

    # --- pas de duplication entre les deux listes ---
    overlap = set(global_keywords) & set(contextual_keywords)
    if overlap:
        errors.append(f"keywords en double entre global et contextual : {overlap}")

    # --- semantic_metadata ---
    if not isinstance(semantic_metadata, dict):
        errors.append("semantic_metadata n'est pas un dict")
    else:
        if not semantic_metadata.get("intent_domain"):
            errors.append("semantic_metadata.intent_domain manquant")
        if not semantic_metadata.get("primary_intent"):
            errors.append("semantic_metadata.primary_intent manquant")

    # --- cache_key ---
    if cache_key is None:
        errors.append("semantic_cache_key est None")
    elif len(cache_key) != 16:
        errors.append(f"semantic_cache_key longueur inattendue : {cache_key!r}")

    return errors


def run():
    node = SemanticAgentNode()
    total_pass = 0
    total_fail = 0

    for scenario in SCENARIOS:
        print(f"\n{'='*60}")
        print(f"SCENARIO {scenario['name']}")
        print("="*60)

        result = node.run(scenario["state"])

        print(f"  semantic_query      : {result.get('semantic_query')}")
        print(f"  global_keywords     : {result.get('global_keywords')}")
        print(f"  contextual_keywords : {result.get('contextual_keywords')}")
        meta = result.get("semantic_metadata", {})
        print(f"  domain              : {meta.get('intent_domain')} | season: {meta.get('seasonal_context')}")
        print(f"  constraints         : {meta.get('constraints_detected')}")
        print(f"  cache_key           : {result.get('semantic_cache_key')}")

        errors = validate(result, scenario["name"], scenario["expect_fallback"])

        if errors:
            total_fail += 1
            print(f"  [FAIL] {len(errors)} erreur(s) :")
            for e in errors:
                print(f"    - {e}")
        else:
            total_pass += 1
            print(f"  [PASS]")

    print(f"\n{'='*60}")
    print(f"RESULTATS : {total_pass} PASS / {total_fail} FAIL")
    print("="*60)


if __name__ == "__main__":
    run()
