from typing import Dict, Any
from app.nodes.core.Base_node import BaseNode,NodeConfig
from app.services.profile_service import ProfileService


class ProfileLoaderNode(BaseNode):
    
    def __init__(self):
        super().__init__(
            NodeConfig(
                name= "ProfileLoaderNode",
                node_type= "technical", )
            )

        
    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:

        traveller_id = state.get("traveller_id")

        if not traveller_id:
            return {
                "profile_data": {}
            }

        traveller_data = ProfileService.get_traveller_profile(traveller_id)

        if not traveller_data:
            return {
                "profile_data": {}
            }

        # -----------------------------
        # Helper
        # -----------------------------
        def safe_get(obj, key, default=None):
            return obj.get(key, default) if obj else default

        def is_family(child, baby):
            return (child or 0) > 0 or (baby or 0) > 0

        # -----------------------------
        # Flight data
        # -----------------------------
        outbound_flight = safe_get(traveller_data, "outboundFlight", {})
        return_flight = safe_get(traveller_data, "returnFlight", {})

        origin = safe_get(
            safe_get(outbound_flight, "takeoffAirport", {})
        )

        destination = safe_get(
            safe_get(outbound_flight, "landingAirport", {})
        )

        # -----------------------------
        # Accommodation
        # -----------------------------
        accommodations = traveller_data.get("accommodations", [])

        main_accommodation = accommodations[0] if accommodations else {}

        hotel = main_accommodation.get("hotel", {})

        # -----------------------------
        # Profile structuré
        # -----------------------------
        profile_data = {

            # -------- identity --------
            "traveller_profile": {
                "first_name": traveller_data.get("firstName"),
                "last_name": traveller_data.get("lastName"),
                "has_partner": traveller_data.get("hasPartner", False),
                "child_count": traveller_data.get("childCount", 0),
                "baby_count": traveller_data.get("babyCount", 0),

                "traveler_type": (
                    "family"
                    if is_family(
                        traveller_data.get("childCount"),
                        traveller_data.get("babyCount")
                    )
                    else "couple"
                    if traveller_data.get("hasPartner")
                    else "solo"
                )
            },

            # -------- travel dates --------
            "availability": {
                "departure_date": traveller_data.get("outboundDate"),
                "return_date": traveller_data.get("returnDate"),
                "duration_days": main_accommodation.get("countNights"),
            },

            # -------- trip route --------
            "route": {
                "origin": origin,
                "destination": destination
            },
            
            # -------- tags --------------
            "tags": {
                "tags": traveller_data.get("tags"),
                "travellerTags": traveller_data.get("travellerTags")
            },

            # -------- preferences --------
            "travel_preferences": {
                "hotel_name": hotel.get("name"),
                "hotel_stars": hotel.get("starsCount", 0),
                "meal_plan": main_accommodation.get("mealPlan"),
                "room_type": main_accommodation.get("roomType", "Standard"),
                "nights": main_accommodation.get("countNights", 0),

                "hotel_level": (
                    "luxury"
                    if hotel.get("starsCount", 0) >= 4
                    else "standard"
                )
            },

        }

        return {
            "profile_data": profile_data
        }