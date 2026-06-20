import logging
import math
from typing import Dict, Any, List, Optional, Tuple
from app.nodes.core.Base_node import BaseNode, NodeConfig
from app.services.hotel_service import HotelService
from app.data.tunisia_destinations import city_to_iata, get_airport_coords

logger = logging.getLogger(__name__)


class HotelNode(BaseNode):

    # =========================================================
    # BUDGET → STARS MAPPING
    # =========================================================

    BUDGET_STARS = {
        "low":     (1, 3),
        "medium":  (3, 4),
        "luxury":  (4, 5),
        "premium": (4, 5),
    }

    # =========================================================
    # KEYWORD → TEXT PATTERNS
    # =========================================================

    KEYWORD_PATTERNS = {
        "spaResort":       ["spa", "thalasso", "hammam", "bien-être", "bien être", "remise en forme"],
        "beachResort":     ["plage", "beach", "bord de mer", "rivage", "sable"],
        "familyResort":    ["famille", "enfants", "kids", "miniclub", "mini-club", "animation"],
        "poolResort":      ["piscine"],
        "golfResort":      ["golf"],
        "relaxingHotel":   ["calme", "reposant", "détente", "paisible", "repos", "sérénité"],
        "allInclusive":    ["tout compris", "all inclusive", "allinclusive", "all-inclusive"],
        "cityHotel":       ["centre ville", "centre-ville", "urbain", "médina"],
        "beachfrontHotel": ["front de mer", "bord de plage", "accès direct", "plage privée"],
        "roomWithView":    ["vue sur", "vue mer", "vue piscine", "balcon", "terrasse"],
        "villasResort":    ["villa", "résidence"],
        "ecoLodge":        ["nature", "écologique", "verdoyant", "jardin"],
        "luxuryHotel":     [],
        "boutiqueHotel":   [],
    }

    def __init__(self):
        super().__init__(
            NodeConfig(
                name="hotel_node",
                node_type="technical",
            )
        )

    # =========================================================
    # MAIN RUN
    # =========================================================

    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:

        # --------------------------------------------------
        # 1. LECTURE STATE
        # --------------------------------------------------
        merged_context  = state.get("merged_context") or {}
        profile_data    = state.get("profile_data") or {}
        user_type       = state.get("user_type", "native")
        global_keywords = state.get("global_keywords") or []
        suggestion_mode = state.get("suggestion_mode", "exploratory")

        destination      = merged_context.get("destination")
        budget_level     = merged_context.get("budget_level")
        is_family        = merged_context.get("is_family", False)

        travel_prefs     = profile_data.get("travel_preferences") or {}
        current_hotel_id = travel_prefs.get("hotel_id") if user_type == "real" else None

        # Coordonnées de référence de la destination (pour distance_km)
        dest_coords = None
        if destination:
            iata = city_to_iata(destination)
            if iata:
                dest_coords = get_airport_coords(iata)

        # --------------------------------------------------
        # 2. TIER 1 — partenaires (1 seul appel)
        # --------------------------------------------------
        try:
            partner_hotels, services_by_hotel = HotelService.get_partner_hotels()
            zones = HotelService.get_zones()
        except Exception as e:
            self.logger.error(f"HotelNode Tier 1 error: {e}")
            return {"hotel_candidates": []}

        # -- Logging Tier 1 coverage --
        self._log_tier1_coverage(partner_hotels, zones)

        # --------------------------------------------------
        # 3. FILTRAGE + SCORING TIER 1
        # --------------------------------------------------
        matched_zone_ids = self._resolve_zone_ids(destination, zones)

        tier1_candidates = self._build_candidates(
            hotels=partner_hotels,
            services_by_hotel=services_by_hotel,
            zones=zones,
            matched_zone_ids=matched_zone_ids,
            budget_level=budget_level,
            current_hotel_id=current_hotel_id,
            destination=destination,
            suggestion_mode=suggestion_mode,
            global_keywords=global_keywords,
            is_family=is_family,
            tier="partner",
            dest_coords=dest_coords,
        )

        # --------------------------------------------------
        # 4. TIER 2 — catalogue complet si < 2 partenaires
        # --------------------------------------------------
        if len(tier1_candidates) < 2:
            logger.info(f"HotelNode: Tier 1 insuffisant ({len(tier1_candidates)}), activation Tier 2")
            try:
                all_hotels = HotelService.get_all_hotels()

                # Exclure les hôtels déjà dans Tier 1
                tier1_ids = {c["id"] for c in tier1_candidates}
                catalogue_hotels = [h for h in all_hotels if h.get("id") not in tier1_ids]

                tier2_candidates = self._build_candidates(
                    hotels=catalogue_hotels,
                    services_by_hotel=services_by_hotel,
                    zones=zones,
                    matched_zone_ids=matched_zone_ids,
                    budget_level=budget_level,
                    current_hotel_id=current_hotel_id,
                    destination=destination,
                    suggestion_mode=suggestion_mode,
                    global_keywords=global_keywords,
                    is_family=is_family,
                    tier="catalogue",
                    dest_coords=dest_coords,
                )

            except Exception as e:
                self.logger.error(f"HotelNode Tier 2 error: {e}")
                tier2_candidates = []
        else:
            tier2_candidates = []

        # --------------------------------------------------
        # 5. FUSION + TRI + TOP 5
        # --------------------------------------------------
        all_candidates = tier1_candidates + tier2_candidates
        all_candidates.sort(key=lambda x: x["score"], reverse=True)
        top5 = all_candidates[:5]

        logger.info(
            f"HotelNode: {len(tier1_candidates)} partenaires + "
            f"{len(tier2_candidates)} catalogue → top {len(top5)}"
        )

        return {"hotel_candidates": top5}

    # =========================================================
    # BUILD CANDIDATES — filtrage + enrichissement + scoring
    # =========================================================

    def _build_candidates(
        self,
        hotels: List[Dict],
        services_by_hotel: Dict[str, List[str]],
        zones: Dict[str, str],
        matched_zone_ids: List[str],
        budget_level: Optional[str],
        current_hotel_id: Optional[str],
        destination: Optional[str],
        suggestion_mode: str,
        global_keywords: List[str],
        is_family: bool,
        tier: str,
        dest_coords: Optional[Tuple[float, float]] = None,
    ) -> List[Dict]:

        stars_range = self.BUDGET_STARS.get(budget_level) if budget_level else None
        dest_lower  = destination.lower().strip() if destination else None
        result      = []

        for hotel in hotels:
            hotel_id = hotel.get("id", "")
            stars    = hotel.get("starsCount", 0) or 0
            zone_id  = hotel.get("zoneId", "")
            address  = (hotel.get("address") or "").lower()

            # filtre : exclure hôtel actuel USER RÉEL
            if current_hotel_id and hotel_id == current_hotel_id:
                continue

            # filtre zone (désactivé si exploratory)
            if suggestion_mode != "exploratory" and dest_lower:
                in_zone    = zone_id in matched_zone_ids
                in_address = dest_lower in address
                if not in_zone and not in_address:
                    continue

            # filtre étoiles
            if stars_range:
                min_s, max_s = stars_range
                if not (min_s <= stars <= max_s):
                    continue

            hotel_services = services_by_hotel.get(hotel_id, [])
            zone_name      = zones.get(zone_id, "")
            coordinates    = self._parse_coordinates(hotel.get("coordinates"))

            distance_km = None
            if dest_coords and coordinates:
                distance_km = self._haversine(
                    coordinates["lat"], coordinates["lng"],
                    dest_coords[0], dest_coords[1],
                )

            business_score = self._compute_business_score(hotel_services, tier)
            user_score     = self._compute_user_score(
                hotel=hotel,
                hotel_services=hotel_services,
                global_keywords=global_keywords,
                budget_level=budget_level,
                is_family=is_family,
            )
            final_score = round(0.7 * user_score + 0.3 * business_score, 4)

            result.append({
                "id":                hotel_id,
                "name":              hotel.get("name", ""),
                "stars":             stars,
                "zone_name":         zone_name,
                "address":           hotel.get("address", ""),
                "short_description": hotel.get("shortDescription", ""),
                "long_description":  hotel.get("longDescription", ""),
                "services":          hotel_services,
                "coordinates":       coordinates,
                "is_partner":        len(hotel_services) > 0,
                "tier":              tier,
                "score":             final_score,
                "business_score":    round(business_score, 4),
                "user_score":        round(user_score, 4),
                "distance_km":       distance_km,
            })

        return result

    # =========================================================
    # TIER 1 COVERAGE LOGGING
    # =========================================================

    def _log_tier1_coverage(
        self,
        partner_hotels: List[Dict],
        zones: Dict[str, str],
    ) -> None:

        unique_zones = {
            zones.get(h.get("zoneId", ""), "inconnue")
            for h in partner_hotels
            if h.get("zoneId")
        }

        logger.info(
            f"HotelNode Tier 1: {len(partner_hotels)} hôtels partenaires | "
            f"{len(unique_zones)} zones : {sorted(unique_zones)}"
        )

        if len(unique_zones) < 5:
            logger.warning(
                f"HotelNode: seulement {len(unique_zones)} zones partenaires "
                f"— Tier 2 sera souvent activé pour les autres destinations"
            )

    # =========================================================
    # ZONE RESOLUTION
    # =========================================================

    def _resolve_zone_ids(
        self,
        destination: Optional[str],
        zones: Dict[str, str],
    ) -> List[str]:

        if not destination:
            return []

        dest_lower = destination.lower().strip()
        return [
            zone_id for zone_id, zone_name in zones.items()
            if dest_lower in zone_name.lower()
        ]

    # =========================================================
    # SCORING
    # =========================================================

    def _compute_business_score(self, hotel_services: List[str], tier: str) -> float:
        if tier == "partner" and hotel_services:
            return 1.0
        if tier == "partner" and not hotel_services:
            return 0.6
        return 0.3

    def _compute_user_score(
        self,
        hotel: Dict,
        hotel_services: List[str],
        global_keywords: List[str],
        budget_level: Optional[str],
        is_family: bool,
    ) -> float:

        stars = hotel.get("starsCount", 0) or 0
        desc  = " ".join([
            (hotel.get("shortDescription") or ""),
            (hotel.get("longDescription") or ""),
            " ".join(hotel_services),
        ]).lower()

        score = 0.0

        # stars match (0.0 → 0.4)
        stars_range = self.BUDGET_STARS.get(budget_level)
        if stars_range:
            min_s, max_s = stars_range
            if min_s <= stars <= max_s:
                score += 0.4
            elif stars >= min_s:
                score += 0.2
        else:
            score += 0.2 + (stars / 5) * 0.2

        # keyword match (0.0 → 0.4)
        if global_keywords:
            matched = 0
            for kw in global_keywords:
                if kw == "luxuryHotel" and stars >= 4:
                    matched += 1
                    continue
                if kw == "boutiqueHotel" and stars <= 3 and hotel.get("shortDescription"):
                    matched += 1
                    continue
                patterns = self.KEYWORD_PATTERNS.get(kw, [])
                if any(p in desc for p in patterns):
                    matched += 1
            score += min(0.4, (matched / len(global_keywords)) * 0.4)

        # family bonus (0.0 → 0.2)
        if is_family:
            if any(p in desc for p in self.KEYWORD_PATTERNS["familyResort"]):
                score += 0.2

        return min(1.0, score)

    # =========================================================
    # HELPERS
    # =========================================================

    @staticmethod
    def _haversine(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
        R = 6371.0
        p1, p2 = math.radians(lat1), math.radians(lat2)
        dp = math.radians(lat2 - lat1)
        dl = math.radians(lng2 - lng1)
        a  = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
        return round(R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a)), 1)

    def _parse_coordinates(self, raw: Any) -> Optional[Dict[str, float]]:
        try:
            if not raw or not isinstance(raw, dict):
                return None
            coords = raw.get("coordinates", [])
            if isinstance(coords, list) and len(coords) == 2:
                return {"lat": coords[1], "lng": coords[0]}  # GeoJSON: [lng, lat]
        except Exception:
            pass
        return None
