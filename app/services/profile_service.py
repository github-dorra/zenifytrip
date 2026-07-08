"""
app/services/profile_service.py

ProfileService — 3 méthodes stateless pour récupérer le profil complet.

Flux :
  1. get_traveller_profile(traveller_id)         → identité + tourOperatorId
  2. get_voucher_id(traveller_id, user_id)       → voucherId filtré par userId
  3. get_travel_plan(voucher_id)                 → planning complet
  4. build_full_profile(traveller_id, user_id)   → profil fusionné complet

CONTRAINTES :
  - Toutes les méthodes sont stateless
  - user_id toujours passé en paramètre (jamais depuis variable globale)
  - Le state LangGraph est la source de vérité — accédé uniquement dans les nodes
"""

import logging                          
from typing import Optional, Dict, Any
import requests
from app.config.settings import (
    TRAVELLER_MANAGEMENT_API_URL,
    TRAVELLER_MANAGEMENT_BY_VOUCHER,
    TRAVEL_PLAN_MANAGEMENT_URL,
    API_KEY,
)

logger = logging.getLogger("services.profile")


def _headers() -> Dict[str, str]:
    """Headers HTTP communs à tous les appels API."""
    return {"Authorization": f"Bearer {API_KEY}"}



# clean data ----------------------------------------------
def _clean_traveller(raw: Dict[str, Any]) -> Dict[str, Any]:
            """
            Ne garde QUE les champs nécessaires au système.
            """

            if not isinstance(raw, dict):
                return {}

            user = raw.get("user") or {}
            tg   = raw.get("touristGroup") or {}
            to   = raw.get("tourOperator") or {}

            return {
                # identity
                "id": raw.get("id"),
                "firstName": raw.get("firstName"),
                "lastName": raw.get("lastName"),
                # user
                "email": user.get("email"),
                "phone": user.get("phone"),
                "address": user.get("address"),

                # tour operator (CRITICAL FIX)
                "tourOperator": {
                    "id": to.get("id"),
                    "name": to.get("name")
                },

                # group travel context
                "touristGroup": {
                    "id": tg.get("id"),
                    "name": tg.get("name"),
                    "outboundDate": tg.get("outboundDate"),
                    "returnDate": tg.get("returnDate"),
                    "destinationCity": tg.get("destinationCity"),
                    "originCity": tg.get("originCity"),
                },
                # optional context
                "agency": raw.get("agency") or {},
                "tags": raw.get("tags") or [],
                "travellerTags": raw.get("travellerTags") or []
            }



def clean_travel_plan(raw: Dict[str, Any]) -> Dict[str, Any]:

    elements = raw.get("elements") or []

    flights = []
    hotels = []
    transfers = []

    for el in elements:

        t = el.get("type")
        data = el.get("data") or {}

        # ───────── FLIGHT ─────────
        if t == "flight":
            flights.append({
                "type": "flight",
                "direction": (data.get("type") or "").lower(),
                "flight_number": data.get("flightNumber"),
                "airline": ((data.get("airlineCompany") or {}).get("fullName")),
                "from": {
                    "name": (data.get("takeoffAirport") or {}).get("name"),
                    "iata": (data.get("takeoffAirport") or {}).get("iataCode"),
                },
                "to": {
                    "name": (data.get("landingAirport") or {}).get("name"),
                    "iata": (data.get("landingAirport") or {}).get("iataCode"),
                },
                "takeoff_time": data.get("takeoffTime"),
                "landing_time": data.get("landingTime"),
            })

        # ───────── HOTEL ─────────
        elif t == "accommodation":
            hotel = data.get("hotel") or {}
            hotelServiceBookings=data.get("hotelServiceBookings") or []
            
            services = []
            for hsb in hotelServiceBookings :
                serviceName = hsb.get("serviceName")
                status = hsb.get("status")
                
                if serviceName:
                    services.append({
                        "name": serviceName,
                        "status": status
                    })
            
            hotels.append({
                "hotel_id": hotel.get("id"),
                "hotel_name": hotel.get("name"),
                "stars": hotel.get("starsCount"),
                "zone": (hotel.get("zone") or {}).get("name"),
                "meal_plan": data.get("mealPlan"),
                "nights": data.get("countNights"),
                "address": hotel.get("address"),
                "descriptions": hotel.get("longDescription"),
                "services": services,
            })
            
                

        # ───────── TRANSFER ─────────
        elif t == "transfer":
            transfers.append({
                "from": (data.get("fromResolved") or {}).get("name"),
                "to": (data.get("toResolved") or {}).get("name"),
                "duration_minutes": data.get("durationMinutes"),
            })

    return {
        "flights": flights,
        "hotels": hotels,
        "transfers": transfers,
    }
    
    
    
# ****************************************************************************** #
class ProfileService:

    # ------------------------------------------------------------------
    # ÉTAPE 1 — Profil voyageur de base
    # ------------------------------------------------------------------

    @staticmethod
    def get_traveller_profile(traveller_id: str) -> Optional[Dict[str, Any]]:
        """
        GET /traveller-management/{traveller_id}
        Retourne le JSON complet ou None si erreur.
        """
        if not traveller_id:
            logger.warning("[ProfileService] get_traveller_profile: traveller_id manquant")
            return None

        try:
            response = requests.get(
                f"{TRAVELLER_MANAGEMENT_API_URL}/{traveller_id}",
                headers=_headers(),
                timeout=50,
            )
            
            response.raise_for_status()
            clean = _clean_traveller(response.json())

            logger.info(f"[API1 CLEAN] traveller_id={traveller_id}")
            return clean

        except requests.HTTPError as e:
            logger.error(f"[ProfileService] HTTP error get_traveller_profile: {e}")
            return None
        except Exception as e:
            logger.error(f"[ProfileService] Error get_traveller_profile: {e}")
            return None
        
        

    # ------------------------------------------------------------------
    # ÉTAPE 2 — Récupération du voucherId
    # ------------------------------------------------------------------

    @staticmethod
    def get_voucher_id(
        traveller_data: dict[str, Any],
        traveller_id: str,
        user_id: str,                       # FIX #2 : paramètre ajouté
    ) -> Optional[str]:
        """
        GET /traveller-management/with-vouchers
        Filtre par userId (priorité absolue) puis travellerId en fallback.

        Args:
            traveller_id : ID du voyageur
            user_id      : ID user connecté depuis le state LangGraph
            
        """

        if not traveller_id or not user_id or not traveller_data:
            logger.warning("[ProfileService] get_voucher_id: paramètres manquants")
            return None

        # Appel 1 — profil de base pour récupérer tourOperatorId + nom
        if not traveller_data:
            logger.error("Traveller API failed → returning EMPTY STRUCTURE")
            traveller_data = {}


        tour_operator_id = traveller_data.get("tourOperator", {}).get("id")
        first_name       = traveller_data.get("firstName", "") or ""
        last_name        = traveller_data.get("lastName",  "") or ""

        if not tour_operator_id:
            logger.warning(f"[ProfileService] tourOperatorId manquant pour {traveller_id}")
            return None

        # Appel 2 — with-vouchers
        try:
            params = {
                "tourOperatorId": tour_operator_id,
                "name":           f"{first_name}".strip() or f"{last_name}".strip(),
                "page":           1,
                "pageSize":       20,
            }

            response = requests.get(
                TRAVELLER_MANAGEMENT_BY_VOUCHER,
                headers=_headers(),
                params=params,
                timeout=30,
            )
            response.raise_for_status()
            data  = response.json()
            groups = data.get("groups") or []

        except requests.HTTPError as e:
            logger.error(f"[ProfileService] HTTP error get_voucher_id: {e}")
            return None
        except Exception as e:
            logger.error(f"[ProfileService] Error get_voucher_id: {e}")
            return None

        # Priorité 1 — filtrage par userId
        for group in groups:

            voucher = group.get("voucher") or {}
            travellers = group.get("travellers") or []

            if not isinstance(voucher, dict):
                continue

            # 1️⃣ match userId dans travellers
            for t in travellers:
                if t.get("userId") == user_id:
                    voucher_id = voucher.get("id")
                    if voucher_id:
                        logger.info(f"[API2] voucher via userId={user_id}")
                        return voucher_id, voucher

            # Priorité 2 — fallback par travellerId
                else :
                    if t.get("id") == traveller_id:
                        voucher_id = voucher.get("id")
                        if voucher_id:
                            logger.info(f"[API2] voucher via travellerId={traveller_id}")
                            return voucher_id, voucher

        logger.warning(
        f"[API2] no voucher found | user_id={user_id} | traveller_id={traveller_id}")
        return None

    # ------------------------------------------------------------------
    # ÉTAPE 3 — Planning de voyage complet by voucherId
    # ------------------------------------------------------------------

    @staticmethod
    def get_travel_plan(voucher_id: str) -> Optional[Dict[str, Any]]:
        """
        GET /travel-plan/voucher/{voucher_id}
        Retourne le planning complet (hôtel, vols, transferts, services réservés).
        """
        if not voucher_id:                          
            logger.warning("[ProfileService] get_travel_plan: voucher_id manquant")
            return None

        try:
            url = f"{TRAVEL_PLAN_MANAGEMENT_URL}/{voucher_id}"

            response = requests.get(
                url,
                headers=_headers(),
                timeout=30,
            )
            response.raise_for_status()
            return response.json()

        except requests.HTTPError as e:
            logger.error(f"[ProfileService] HTTP error get_travel_plan: {e}")  # FIX #8
            return None
        except Exception as e:
            logger.error(f"[ProfileService] Error get_travel_plan: {e}")        # FIX #8
            return None

    # ------------------------------------------------------------------
    # ÉTAPE 4 — Profil complet fusionné (orchestrateur)
    # ------------------------------------------------------------------

    @staticmethod
    def build_full_profile(
        traveller_id: str,
        user_id: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Orchestre les 3 appels pour construire le profil enrichi complet.
        Appelé par ProfileCacheService à l'authentification.

        Returns:
            {traveller_data, travel_plan, voucher_id} ou None si échec critique.
        """
        if not traveller_id or not user_id:
            logger.warning("[ProfileService] build_full_profile: paramètres manquants")
            return None

        # Appel 1 — profil de base
        traveller_data = ProfileService.get_traveller_profile(traveller_id)
        logger.info(f"[DEBUG STEP 1] traveller_data type = {type(traveller_data)}")
        
        if not traveller_data:
            logger.error(f"[ProfileService] Profil introuvable: {traveller_id}")
            return None
        
        voucher_id = None
        voucher_data = {}
        travel_plan = None

        # Appel 2 — voucherId + données du voucher (childCount, babyCount, adultCount)
        try:
            result = ProfileService.get_voucher_id(traveller_data, traveller_id, user_id)
            voucher_id, voucher_data = result if result else (None, {})
        except Exception as e:
            logger.error(f"[ProfileService] Error get_voucher_id: {e}")
            voucher_id, voucher_data = None, {}


        if voucher_id:
            try:
                travel_plan = ProfileService.get_travel_plan(voucher_id)
            except Exception as e:
                logger.warning(f"travel_plan error: {e}")

        
            logger.info(
            f"[ProfileService] Profil complet — "
            f"traveller_id={traveller_id} | voucher_id={voucher_id} | "
            f"travel_plan={'OK' if travel_plan else 'MANQUANT'}"
            )
        return {
            "traveller_data": traveller_data,
            "travel_plan":    travel_plan,
            "voucher_id":     voucher_id,
            "voucher_data":   voucher_data,
        }
        


