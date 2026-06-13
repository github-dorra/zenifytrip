"""
AvailabilityCheckerNode — Phase 1 (après profile_loader)
=========================================================
Détermine si le voyageur est en voyage actif et extrait la destination
réelle depuis l'hôtel (3 niveaux) ou la géolocalisation.

Entrée  : profile_data, travellerId, intent_result, user_geolocation
Sortie  : traveller_available, availability_result
"""
from typing import Any, Dict

from app.nodes.core.Base_node import BaseNode, NodeConfig
from app.services.availability_service import check_availability


class AvailabilityCheckerNode(BaseNode):

    def __init__(self):
        super().__init__(
            NodeConfig(
                name="availability_checker",
                node_type="technical",
            )
        )

    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        traveller_id  = state.get("travellerId") or ""
        profile_data  = state.get("profile_data") or {}
        geolocation   = state.get("user_geolocation")       # {lat, lng} ou None

        # Date de référence depuis les contraintes si disponible
        intent      = state.get("intent_result") or {}
        constraints = intent.get("constraints")  or {}
        request_date = constraints.get("start_date")

        try:
            result = check_availability(
                traveller_id=traveller_id or None,
                profile_data=profile_data,
                request_date=request_date,
                geolocation=geolocation,
            )
        except Exception as e:
            self.logger.error(f"[AvailabilityCheckerNode] erreur: {e}")
            result = {
                "trip_is_ongoing":     False,
                "outbound_date":       None,
                "return_date":         None,
                "days_remaining":      None,
                "hotel_name":          None,
                "destination":         None,
                "destination_source":  None,
                "booked_activity_ids": [],
                "booked_time_slots":   [],
            }

        self.logger.info(
            f"[AvailabilityCheckerNode] "
            f"trip_is_ongoing={result.get('trip_is_ongoing')} | "
            f"destination={result.get('destination')!r} "
            f"(source={result.get('destination_source')}) | "
            f"geoloc={'oui' if geolocation else 'non'}"
        )

        return {
            "traveller_available": result.get("trip_is_ongoing", False),
            "availability_result": result,
        }
