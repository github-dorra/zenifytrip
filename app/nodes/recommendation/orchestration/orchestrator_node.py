from typing import Dict, Any, List

from app.nodes.core.Base_node import BaseNode, NodeConfig


# ── MAPPING INTENT → SERVICES ────────────────────────────────────────────────
# Ordre dans les listes = ordre de dépendance logique.
# LangGraph les exécute en parallèle ; l'ordre ici sert à la lisibilité des logs
# et garantit un résultat stable si on passe en séquentiel.

INTENT_TO_SERVICES: Dict[str, List[str]] = {
    "accommodation_recommendation":  ["hotel_node"],
    "flight_recommendation":         ["flight_node"],
    "restaurant_recommendation":     ["restaurant_node"],
    "activity_recommendation":       ["activity_node"],
    # day_planning a besoin de contexte hôtel + activités + restos
    "day_planning":                  ["hotel_node", "activity_node", "restaurant_node"],
    # package complet = les 4 domaines
    "trip_package_recommendation":   ["flight_node", "hotel_node", "activity_node", "restaurant_node"],
    # intents conversationnels → pas de domaine
    "travel_question":               [],
    "booking_question":              [],
    "profile_update":                [],
    "feedback":                      [],
    "greeting":                      [],
    "unsupported":                   [],
}

# Ordre de priorité global (flight avant hotel avant activities avant resto)
SERVICE_ORDER = ["flight_node", "hotel_node", "activity_node", "restaurant_node"]

# Mapping secondary_intent → service ajouté
SECONDARY_TO_SERVICE: Dict[str, str] = {
    "accommodation_recommendation": "hotel_node",
    "flight_recommendation":        "flight_node",
    "restaurant_recommendation":    "restaurant_node",
    "activity_recommendation":      "activity_node",
}


class OrchestratorNode(BaseNode):
    """
    Planner technique (sans LLM) — décide quels services appeler.

    Lit merged_context + intent_result + suggestion_mode.
    Écrit requested_services dans le state.
    La fonction de routage dans builder.py exécute le fan-out LangGraph.
    """

    def __init__(self):
        super().__init__(
            NodeConfig(
                name="orchestrator",
                node_type="technical",
            )
        )

    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:

        # ── 1. EXTRACTION ────────────────────────────────────────────────────
        merged_context  = state.get("merged_context") or {}
        intent_result   = state.get("intent_result") or {}
        suggestion_mode = state.get("suggestion_mode") or "exploratory"

        # primary_intent : priorité à intent_result, fallback merged_context
        primary_intent = (
            intent_result.get("primary_intent")
            or merged_context.get("primary_intent")
            or "unsupported"
        )

        secondary_intents = (
            intent_result.get("secondary_intents")
            or merged_context.get("secondary_intents")
            or []
        )

        constraints = merged_context.get("constraints") or {}
        destination = (
            constraints.get("destination")
            or merged_context.get("destination")
        )

        # ── 2. SERVICES DE BASE (intent primaire) ────────────────────────────
        services: set = set(INTENT_TO_SERVICES.get(primary_intent, []))

        # ── 3. ENRICHISSEMENT PAR INTENTS SECONDAIRES ────────────────────────
        for intent in secondary_intents:
            svc = SECONDARY_TO_SERVICE.get(intent)
            if svc:
                services.add(svc)

        # ── 4. RÈGLES MÉTIER ─────────────────────────────────────────────────

        # day_planning : garantit toujours activity + restaurant
        if primary_intent == "day_planning":
            services |= {"activity_node", "restaurant_node"}

        # trip_package avec destination connue → activer les 4 services
        if primary_intent == "trip_package_recommendation" and destination:
            services = set(SERVICE_ORDER)

        # mode exploratory avec hôtel seul → ajouter activités pour la découverte
        if suggestion_mode == "exploratory" and services == {"hotel_node"}:
            services.add("activity_node")

        # ── 5. ORDONNANCEMENT STABLE ─────────────────────────────────────────
        # flight → hotel → activity → restaurant (dépendance logique)
        ordered: List[str] = [s for s in SERVICE_ORDER if s in services]

        # ── 6. LOG ───────────────────────────────────────────────────────────
        self.logger.info(
            f"Orchestrator: intent={primary_intent} | "
            f"secondary={secondary_intents} | "
            f"mode={suggestion_mode} | "
            f"destination={destination!r} | "
            f"services={ordered}"
        )

        return {"requested_services": ordered}
