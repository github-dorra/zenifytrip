#couche d'accès aux données hôtel. Gère pagination, cache, et le pattern Tier 1/Tier2.

import requests
from typing import Dict, List, Any, Tuple
from app.config.settings import HOTEL_API_URL, HOTEL_SERVICE_API_URL, ZONES_API_URL, API_KEY
from app.services.cache_service import cache, SimpleTTLCache


class HotelService:

    @staticmethod
    def _headers() -> Dict[str, str]:
        return {"Authorization": f"Bearer {API_KEY}"}

    # =========================================================
    # TIER 1 — 1 SEUL APPEL : partenaires + services embarqués
    # =========================================================

    @staticmethod
    def get_partner_hotels() -> Tuple[List[Dict[str, Any]], Dict[str, List[str]]]:
        """
        Retourne (partner_hotels, services_by_hotel) en un seul appel API.
        Les données hôtel sont extraites du champ 'hotel' embarqué dans chaque service.
        TTL : 2h (services agence mis à jour fréquemment).
        """
        cached = cache.get("partner_hotels")
        if cached is not None:
            return cached["hotels"], cached["services"]

        hotels_by_id: Dict[str, Dict[str, Any]] = {}
        services_by_hotel: Dict[str, List[str]] = {}

        try:
            response = requests.get(
                HOTEL_SERVICE_API_URL,
                headers=HotelService._headers(),
                timeout=30,
            )
            response.raise_for_status()
            data = response.json()

            for item in data.get("results", []):
                hotel_id    = item.get("hotelId")
                service     = item.get("service") or {}
                service_name = service.get("name")
                hotel_data  = item.get("hotel") or {}
                available   = item.get("available", False)

                if not hotel_id or not hotel_data:
                    continue

                # Extraire hôtel embarqué (1 seul appel — pas de GET /api/hotels/{id})
                if hotel_id not in hotels_by_id:
                    hotels_by_id[hotel_id] = hotel_data

                # Agréger les services disponibles
                if service_name and available:
                    if hotel_id not in services_by_hotel:
                        services_by_hotel[hotel_id] = []
                    if service_name not in services_by_hotel[hotel_id]:
                        services_by_hotel[hotel_id].append(service_name)

        except Exception as e:
            print(f"[HotelService] get_partner_hotels error: {e}")

        partner_hotels = list(hotels_by_id.values())

        cache.set(
            "partner_hotels",
            {"hotels": partner_hotels, "services": services_by_hotel},
            SimpleTTLCache.TTL_HOTEL_SERVICES,
        )

        return partner_hotels, services_by_hotel

    # =========================================================
    # TIER 2 — Catalogue complet (fallback) + cache 24h
    # =========================================================

    @staticmethod
    def get_all_hotels() -> List[Dict[str, Any]]:
        cached = cache.get("hotels")
        if cached is not None:
            return cached

        all_hotels = []
        take = 500
        skip = 0

        try:
            while True:
                response = requests.get(
                    HOTEL_API_URL,
                    headers=HotelService._headers(),
                    params={"take": take, "skip": skip},
                    timeout=30,
                )
                response.raise_for_status()
                data = response.json()

                results = data.get("results", [])
                all_hotels.extend(results)

                total = data.get("inlineCount", 0)
                skip += take

                if skip >= total or not results:
                    break

        except Exception as e:
            print(f"[HotelService] get_all_hotels error: {e}")

        cache.set("hotels", all_hotels, SimpleTTLCache.TTL_HOTELS)
        return all_hotels

    # =========================================================
    # ZONES — id → name + cache 24h
    # =========================================================

    @staticmethod
    def get_zones() -> Dict[str, str]:
        cached = cache.get("zones")
        if cached is not None:
            return cached

        zones: Dict[str, str] = {}

        try:
            response = requests.get(
                ZONES_API_URL,
                headers=HotelService._headers(),
                timeout=30,
            )
            response.raise_for_status()
            data = response.json()

            results = data if isinstance(data, list) else data.get("results", [])

            for zone in results:
                zone_id   = zone.get("id")
                zone_name = zone.get("name")
                if zone_id and zone_name:
                    zones[zone_id] = zone_name

        except Exception as e:
            print(f"[HotelService] get_zones error: {e}")

        cache.set("zones", zones, SimpleTTLCache.TTL_ZONES)
        return zones
