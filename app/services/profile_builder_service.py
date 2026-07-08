"""
app/services/profile_builder_service.py
═══════════════════════════════════════════════════════════════════════════════
RÔLE ET INTÉRÊT
───────────────
Ce fichier est le CONSTRUCTEUR DU PROFIL ENRICHI.
 
Il orchestre 3 appels API séquentiels et fusionne les résultats en 1 objet
structuré et complet, prêt à être stocké dans Redis.
 
POURQUOI CE FICHIER EXISTE :
  - profile_service.py   → fait les appels HTTP bruts (données brutes)
  - profile_builder_service.py → FUSIONNE + STRUCTURE les données des 2 APIs
  - profile_cache_service.py  → STOCKE/LIT depuis Redis
 
SÉPARATION DES RESPONSABILITÉS :
  profile_service     = HTTP layer    (appels API)
  profile_builder     = Business layer (fusion + structuration)
  profile_cache       = Cache layer   (Redis TTL)
 
DONNÉES QU'IL PRODUIT (stockées dans Redis) :
  ┌─────────────────────────────────────────────────────┐
  │ identity      : nom, prénom, titre, genre, email    │
  │ group         : hasPartner, childCount, babyCount   │
  │                 → traveler_type calculé             │
  │ trip          : outbound_date, return_date,         │
  │                 duration_days                       │
  │ route         : origin, destination (vraie zone)    │
  │ accommodation : hotel complet, meal_plan, nights    │
  │                 booked_service_names (à exclure)    │
  │ flights       : outbound{} + return{}               │
  │ transfer      : aéroport → hôtel                    │
  │ context       : agence, tour_operator, groupe       │
  │ tags          : préférences voyageur                │
  │ meta          : voucher_id, cached_at, ttl_reason   │
  └─────────────────────────────────────────────────────┘
 
TTL REDIS :
  Calculé dynamiquement depuis returnDate du contrat.
  Si returnDate dans le futur → TTL = (returnDate - now) + 7 jours buffer.
  Sinon (voyage passé) → TTL = 7 jours.
  Maximum : 30 jours.
"""



import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
 
from app.services.profile_service import ProfileService
from app.config.settings import ( PROFILE_CACHE_EXTRA_SECONDS_AFTER_RETURN , PROFILE_CACHE_MAX_TTL_SECONDS)

logger = logging.getLogger("services.profile_builder")

class ProfileBuilderService:
    # Point d'entrée principal ---------------------------------------------------
    @staticmethod
    def build(traveller_id: str, user_id: str) -> Optional[Dict[str, Any]]:
        """
        Construit le profil complet enrichi depuis les 2 APIs.
        Appelé par ProfileCacheService.on_user_login() à l'authentification.
 
        Args:
            traveller_id : ID du voyageur (depuis state LangGraph)
            user_id      : ID user connecté (depuis state LangGraph)
 
        Returns:
            Dict profil structuré complet ou None si échec critique.
        """
        if not traveller_id or not user_id:
            logger.warning("[ProfileBuilder] build: paramètres manquants")
            return None
 
        logger.info(f"[ProfileBuilder] Construction profil — traveller_id={traveller_id}")
 
        # ── Appel orchestrateur ProfileService ────────────────────────────
        raw = ProfileService.build_full_profile(
                traveller_id=traveller_id,
                user_id=user_id,
            )
        logger.debug(f"[BUILDER RAW TYPE] {type(raw)}")
        logger.debug(f"[BUILDER RAW KEYS] {raw.keys() if isinstance(raw, dict) else 'NOT DICT'}")

        if not raw:
            logger.error(f"[ProfileBuilder] Aucune donnée API pour {traveller_id}")
            return None
 
        # 🔴 IMPORTANT : on garde EXACTEMENT le même format
        traveller_data = raw.get("traveller_data")
        if not isinstance(traveller_data, dict):
            traveller_data = {}

        travel_plan = raw.get("travel_plan")
        if not isinstance(travel_plan, dict):
            travel_plan = {}

        voucher_id   = raw.get("voucher_id")
        voucher_data = raw.get("voucher_data") or {}

        elements = travel_plan.get("elements") or []
        accommodation_el, outbound_flight, return_flight, transfer_el = ProfileBuilderService._parse_elements(elements)

        tourist_group = traveller_data.get("touristGroup") or {}
        agency = traveller_data.get("agency") or {}
        tour_operator = traveller_data.get("tourOperator") or {}
        user_obj = traveller_data.get("user") or {}
        
        
        # ── Construire chaque section ──────────────────────────────────────
        identity = ProfileBuilderService._build_identity(traveller_data, user_obj)
        group    = ProfileBuilderService._build_group(voucher_data)
        trip = ProfileBuilderService._build_trip(traveller_data, tourist_group, accommodation_el)
        route = ProfileBuilderService._build_route(outbound_flight, transfer_el, tourist_group, accommodation_el)
        accommodation = ProfileBuilderService._build_accommodation(accommodation_el)
        flights = ProfileBuilderService._build_flights(outbound_flight, return_flight)
        transfer = ProfileBuilderService._build_transfer(transfer_el)
        context = ProfileBuilderService._build_context(tourist_group, agency, tour_operator)
        tags = ProfileBuilderService._build_tags(traveller_data)
 
        ttl_seconds, ttl_reason = ProfileBuilderService._compute_ttl(
            trip.get("return_date") )
        
        
 
        # ── Profil final ───────────────────────────────────────────────────
        
        profile = {

            # 🔽 enrichissement (nouveau mais compatible)
            "identity": identity,
            "group": group,
            "trip": trip,
            "route": route,
            "accommodation": accommodation,
            "flights": flights,
            "transfer": transfer,
            "context": context,
            "tags": tags,
            
            "meta": {
                "traveller_id": traveller_id,
                "voucher_id": voucher_id,
                "cached_at": datetime.now(timezone.utc).isoformat(),
                "ttl_seconds": ttl_seconds,
                "ttl_reason": ttl_reason,
            }
        }

        return {
            "profile": profile,
            "ttl_seconds": ttl_seconds
        }

    # ──────────────────────────────────────────────────────────────────────
    # TTL
    # ──────────────────────────────────────────────────────────────────────
    @staticmethod
    def _compute_ttl(return_date_str: Optional[str]) -> tuple:

        fallback = PROFILE_CACHE_EXTRA_SECONDS_AFTER_RETURN
        reason = "default_buffer"

        if not return_date_str:
            return fallback, reason

        try:
            fmt = "%Y-%m-%dT%H:%M:%S.%fZ"
            return_dt = datetime.strptime(return_date_str[:26] + "Z", fmt)
            return_dt = return_dt.replace(tzinfo=timezone.utc)

            now = datetime.now(timezone.utc)

            if return_dt > now:
                seconds_until = (return_dt - now).total_seconds()

                ttl = min(
                    seconds_until + PROFILE_CACHE_EXTRA_SECONDS_AFTER_RETURN,
                    PROFILE_CACHE_MAX_TTL_SECONDS
                )

                return int(ttl), "return_date_dynamic"

            return fallback, "trip_past"

        except Exception as e:
            logger.warning(f"[TTL ERROR] {e}")
            return fallback, reason
    

    # PARSER IDENTIQUE -------------------------------------------------------------
    
    @staticmethod
    def _parse_elements(elements: List[Dict]):
        accommodation_el = {}
        outbound = {}
        ret = {}
        transfer = {}

        for el in elements:
            t = el.get("type")
            data = el.get("data") or {}

            if t == "accommodation" and not accommodation_el:
                accommodation_el = data

            elif t == "flight":
                if data.get("type") == "Outbound":
                    outbound = data
                elif data.get("type") == "Return":
                    ret = data

            elif t == "transfer" and not transfer:
                transfer = data

        return accommodation_el, outbound, ret, transfer
    
    
     # LES AUTRES BUILDERS (inchangés) -----------------------------------------------
    @staticmethod
    def _build_identity(td, user):
        return {
            "traveller_id": td.get("id"),
            "first_name": td.get("firstName"),
            "last_name": td.get("lastName"),
            "email": td.get("email") or user.get("email"),
            "phone": td.get("phone") or user.get("phone"),
        }

 
    @staticmethod
    def _build_group(v: Dict):
        child = int(v.get("childCount") or 0)
        baby  = int(v.get("babyCount")  or 0)
        adult = int(v.get("adultCount") or 1)
        has_partner = adult > 1

        if child or baby:
            t = "family"
        elif has_partner:
            t = "couple"
        else:
            t = "solo"

        return {
            "has_partner":   has_partner,
            "child_count":   child,
            "baby_count":    baby,
            "traveler_type": t,
        }

    @staticmethod
    def _build_trip(td: Dict, tg: Dict, accom: Dict) -> Dict:
        outbound_date = td.get("outboundDate") or tg.get("outboundDate")
        return_date   = td.get("returnDate")   or tg.get("returnDate")
 
        try:
            nights = int(accom.get("countNights") or 0)
        except (ValueError, TypeError):
            nights = 0
 
        duration_days = nights or ProfileBuilderService._date_diff(outbound_date, return_date)
 
        return {
            "outbound_date": outbound_date,
            "return_date":   return_date,
            "duration_days": duration_days,
            "checkin_date":  accom.get("date"),
        }

    @staticmethod
    def _build_route(outbound: Dict, transfer: Dict, tg: Dict, accom: Dict) -> Dict:
        def s(o, k): return o.get(k) if isinstance(o, dict) else None
 
        hotel = accom.get("hotel") or {}
 
        # Destination : hotel.zone → transfer.toResolved → touristGroup
        destination = (
            s(s(hotel, "zone"), "name")
            or s(s(transfer, "toResolved"), "name")
            or tg.get("destinationCity")
        )
 
        # Origin : outbound takeoffAirport → transfer fromResolved → touristGroup
        origin = (
            s(s(outbound, "takeoffAirport"), "name")
            or s(s(transfer, "fromResolved"), "name")
            or tg.get("originCity")
        )
 
        return {
            "origin":      origin,
            "destination": destination,
        }
 
    @staticmethod
    def _build_accommodation(accom: Dict) -> Dict:
        if not accom:
            return {}
 
        hotel = accom.get("hotel") or {}
 
        try:
            stars = int(hotel.get("starsCount") or 0)
        except:
            stars = 0
 
        # Services déjà réservés → à exclure des recommandations
        booked_services: List[Dict] = []
        booked_service_names: List[str] = []
 
        for b in (accom.get("hotelServiceBookings") or []):
            name = b.get("serviceName")
            if name:
                booked_services.append({
                    "name":   name,
                    "date":   b.get("date"),
                    "status": b.get("status"),
                })
                booked_service_names.append(name)
 
        return {
            "hotel_id":            hotel.get("id"),
            "hotel_name":          hotel.get("name"),
            "hotel_stars":         stars,
            "hotel_level":         "luxury" if stars >= 4 else "standard",
            "hotel_description":   hotel.get("shortDescription"),
            "hotel_address":       hotel.get("address"),
            "hotel_zone":          (hotel.get("zone") or {}).get("name"),
            "meal_plan":           accom.get("mealPlan"),
            "room_type":           accom.get("roomType", "Standard"),
            "nights":              accom.get("countNights", 0),
            "booked_services":     booked_services,
            "booked_service_names": booked_service_names,
        }
 
    @staticmethod
    def _build_flights(outbound: Dict, ret: Dict) -> Dict:
        def airport(flight: Dict, key: str) -> Dict:
            ap = (flight.get(key) or {})
            return {"name": ap.get("name"), "iata": ap.get("iataCode")}
 
        return {
            "outbound": {
                "flight_number": outbound.get("flightNumber"),
                "airline":       (outbound.get("airlineCompany") or {}).get("fullName"),
                "from":          airport(outbound, "takeoffAirport"),
                "to":            airport(outbound, "landingAirport"),
                "takeoff_time":  outbound.get("takeoffTime"),
                "landing_time":  outbound.get("landingTime"),
                "schedule":      outbound.get("scheduleStatus"),
            } if outbound else {},
 
            "return": {
                "flight_number": ret.get("flightNumber"),
                "from":          airport(ret, "takeoffAirport"),
                "to":            airport(ret, "landingAirport"),
                "takeoff_time":  ret.get("takeoffTime"),
                "landing_time":  ret.get("landingTime"),
                "schedule":      ret.get("scheduleStatus"),
                "notes":         ret.get("notes"),
            } if ret else {},
        }
 
    @staticmethod
    def _build_transfer(transfer: Dict) -> Dict:
        if not transfer:
            return {}
        return {
            "title":            transfer.get("title"),
            "from":             (transfer.get("fromResolved") or {}).get("name"),
            "to":               (transfer.get("toResolved") or {}).get("name"),
            "duration_minutes": transfer.get("durationMinutes"),
            "type":             transfer.get("type"),
        }
 
    @staticmethod
    def _build_context(tg: Dict, agency: Dict, to: Dict) -> Dict:
        return {
            "tourist_group_id":    tg.get("id"),
            "tourist_group_name":  tg.get("name"),
            "agency_name":         agency.get("fullName") or agency.get("name"),
            "tour_operator_name":  to.get("fullName")     or to.get("name"),
        }
 
    @staticmethod
    def _build_tags(td: Dict) -> Dict:
        raw_tags = td.get("tags") or []
        tags     = raw_tags if isinstance(raw_tags, list) else []
        traveller_tags = [
            t.get("tag") if isinstance(t, dict) else t
            for t in (td.get("travellerTags") or [])
        ]
        return {"tags": tags, "traveller_tags": traveller_tags}
 
    # ──────────────────────────────────────────────────────────────────────
    # Helpers
    # ──────────────────────────────────────────────────────────────────────

    @staticmethod
    def _date_diff(d1_str: Optional[str], d2_str: Optional[str]) -> Optional[int]:
        """Calcule la différence en jours entre deux dates ISO."""
        if not d1_str or not d2_str:
            return None
        try:
            fmt = "%Y-%m-%dT%H:%M:%S.%fZ"
            d1 = datetime.strptime(d1_str[:26] + "Z", fmt)
            d2 = datetime.strptime(d2_str[:26] + "Z", fmt)
            delta = (d2 - d1).days
            return max(1, delta) if delta > 0 else None
        except Exception:
            return None
