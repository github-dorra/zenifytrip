from typing import Dict, Any
from app.nodes.core.Base_node import BaseNode, NodeConfig
from app.services.profile_cache_service import ProfileCacheService

class ProfileLoaderNode(BaseNode):
    
    def __init__(self):
        super().__init__(
            NodeConfig(
                name= "ProfileLoaderNode",
                node_type= "technical", )
            )

        
    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:

        traveller_id = state.get("travellerId")
        user_id      = state.get("user_id")

        if not traveller_id:
            self.logger.info("[ProfileLoaderNode] Pas de travellerId → USER NATIF")
            return {
                "profile_data": {}, 
                "user_type": "native"
                }
            
        
        # ── LECTURE CACHE REDIS ───────────────────────────────────────────
        cached_profile = ProfileCacheService.get_profile(traveller_id)
        
        
        # ── CACHE MISS → build complet depuis API + cache avec TTL dynamique ─
        profile = None

        if cached_profile:
            profile = cached_profile
        else:
            profile = ProfileCacheService.on_user_login(
                traveller_id=traveller_id,
                user_id=user_id,
            )

        if not profile:
            return {"profile_data": {}, "user_type": "native"}
        
        # ── STRUCTURE OUTPUT ──────────────────
        profile_data = {

            # API 1 — GET /traveller-management/{traveller_id}
            # identity : first_name, last_name, email, phone
            # group    : has_partner*, child_count*, baby_count*, traveler_type*
            #            (*) child_count/baby_count/traveler_type → API 2 (voucher)
            "traveller_profile": {
                **profile.get("identity", {}),
                **profile.get("group", {}),
            },

            # API 3 — GET /travel-plan-management/voucher/{voucher_id}
            # outbound_date, return_date, duration_days, checkin_date
            "availability": profile.get("trip", {}),

            # API 1 (touristGroup) + API 3 (takeoffAirport / hotel.zone)
            # origin : takeoffAirport.name du vol aller
            # destination : hotel.zone.name de l'hébergement
            "route": profile.get("route", {}),

            "travel_preferences": {
                # API 3 — elements[type=accommodation]
                # hotel_name, hotel_stars, hotel_zone, meal_plan, nights
                # booked_services : services déjà réservés (name, date, status)
                "accommodation": profile.get("accommodation", {}),

                # API 3 — elements[type=flight]
                # outbound : flight_number, airline, from/to IATA, takeoff/landing_time
                # return   : flight_number, from/to IATA, takeoff/landing_time, notes
                "flights": profile.get("flights", {}),

                # API 3 — elements[type=transfer]
                # from, to, duration_minutes, type
                "transfer": profile.get("transfer", {}),
            },

            # API 1 — touristGroup + agency + tourOperator
            "tourist_group": profile.get("context", {}),

            # API 1 — tags[] + travellerTags[]
            "tags": profile.get("tags", {}),

            # API 2 — voucher.id
            "voucher_id": profile.get("meta", {}).get("voucher_id"),
        }

        return {
            "profile_data": profile_data,
            "user_type": "real"
        }