from typing import Dict, Any, List

from app.nodes.core.Base_node import BaseNode, NodeConfig
from app.schemas.flight_schema import FlightCandidate, FlightNodeOutput
from app.services.flight_service import FlightService


class FlightNode(BaseNode):

    def __init__(self):
        super().__init__(
            NodeConfig(
                name="flight_node",
                node_type="technical",
            )
        )

    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:


        # 1. EXTRACTION SÉCURISÉE
        
        merged_context  = state.get("merged_context") or {}
        constraints     = merged_context.get("constraints") or {}
        suggestion_mode = state.get("suggestion_mode") or "exploratory"
        profile_data    = state.get("profile_data") or {}

        # En mode exploratory sans destination → on élargit la recherche
        max_candidates = 15 if suggestion_mode == "exploratory" else 10

        # --------------------------------------------------------
        # 2. APPEL SERVICE — Tier 1 (profil) → Tier 2 (catalogue)
        # --------------------------------------------------------
        try:
            raw_candidates = FlightService.get_flight_candidates(
                constraints=constraints,
                profile_data=profile_data,
                max_candidates=max_candidates,
            )
        except Exception as e:
            self.logger.error(f"FlightService error: {e}")
            raw_candidates = []

        # --------------------------------------------------------
        # 3. VALIDATION PYDANTIC — chaque candidat
        # --------------------------------------------------------
        validated: List[Dict[str, Any]] = []
        validation_failures = 0

        for raw in raw_candidates:
            try:
                candidate = FlightCandidate(**raw)
                validated.append(candidate.model_dump())
            except Exception as e:
                validation_failures += 1
                self.logger.warning(f"FlightCandidate validation skip: {e}")

        # --------------------------------------------------------
        # 4. CONFIANCE DU NODE
        # --------------------------------------------------------
        destination = (constraints.get("destination") or "").strip()
        required_fields_score   = 1.0 if destination else 0.5
        schema_validation_score = 1.0 if validation_failures == 0 else 0.6
        source_reliability      = 1.0 if validated else 0.0

        confidence = self.calculate_confidence(
            model_confidence=0.0,
            required_fields_score=required_fields_score,
            schema_validation_score=schema_validation_score,
            source_reliability_score=source_reliability,
        )

        # --------------------------------------------------------
        # 5. BUILD OUTPUT + LOGS
        # --------------------------------------------------------
        filters_applied = []
        if destination:
            filters_applied.append(f"destination:{destination}")
        origin = (constraints.get("origin") or "").strip()
        if origin:
            filters_applied.append(f"origin:{origin}")
        flight_pref = constraints.get("flight_preferences") or {}
        if flight_pref.get("flight_type"):
            filters_applied.append(f"type:{flight_pref['flight_type']}")

        try:
            output = FlightNodeOutput(
                flight_candidates=[FlightCandidate(**c) for c in validated],
                total_found=len(validated),
                filters_applied=filters_applied,
                confidence=confidence,
            )
        except Exception as e:
            self.logger.error(f"FlightNodeOutput build error: {e}")
            output = FlightNodeOutput()

        tier1_count = sum(1 for c in validated if c.get("tier") == "profile")
        tier2_count = output.total_found - tier1_count

        self.logger.info(
            f"candidates={output.total_found} "
            f"(tier1_profile={tier1_count}, tier2_catalogue={tier2_count}) | "
            f"mode={suggestion_mode} | "
            f"confidence={output.confidence} | "
            f"filters={filters_applied}"
        )

        # --------------------------------------------------------
        # 6. RETOURNER UNIQUEMENT LES CLÉS MISES À JOUR
        # --------------------------------------------------------
        return {
            "flight_candidates": [c.model_dump() for c in output.flight_candidates],
        }
