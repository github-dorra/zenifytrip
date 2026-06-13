"""
AvailabilityService — Vérification disponibilité voyageur
==========================================================
Détermine la destination réelle via 3 niveaux de fallback :
  Niveau 1 — hotel.address (dict structuré, plusieurs clés possibles)
  Niveau 2 — hotel.address (string) ou hotel.name (scan ville connue)
  Niveau 3 — géolocalisation GPS → ville tunisienne la plus proche

Source : GET /api/bookings?travellerId={id}
"""
import logging
import math
import unicodedata
import requests
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Set, Tuple

from app.config.settings import BOOKINGS_API_URL, API_KEY
from app.services.cache_service import SimpleTTLCache, cache

logger = logging.getLogger(__name__)

HEADERS  = {"Authorization": f"Bearer {API_KEY}"}
TIMEOUT  = 15
MAX_GEOLOC_RADIUS_KM = 200   # au-delà → pas de correspondance


# ─── Utilitaires texte ────────────────────────────────────────────────────────

def _normalize(text: str) -> str:
    """Lowercase + supprime les accents (unicode NFKD)."""
    nfkd = unicodedata.normalize("NFKD", str(text).lower())
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def _haversine(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Distance en km entre deux points GPS."""
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1))
         * math.cos(math.radians(lat2))
         * math.sin(dlng / 2) ** 2)
    return R * 2 * math.asin(math.sqrt(a))


# ─── Niveau 2 — scan texte → ville connue ────────────────────────────────────

def _match_city_in_text(text: str) -> Optional[str]:
    """
    Cherche un nom de ville tunisienne connu dans un texte libre.
    Retourne le nom canonique (ex: "Sousse", "Hammamet / Nabeul").
    Prend le match le plus long pour éviter "el" dans "el kantaoui".
    """
    from app.data.tunisia_destinations import CITY_TO_IATA, TUNISIA_DESTINATIONS

    normalized_text = _normalize(text)
    best_city: Optional[str] = None
    best_len: int = 0

    for city_key, iata in CITY_TO_IATA.items():
        norm_key = _normalize(city_key)
        if len(norm_key) < 3:          # ignorer clés trop courtes ("el", "le")
            continue
        if norm_key in normalized_text and len(norm_key) > best_len:
            canonical = TUNISIA_DESTINATIONS.get(iata, {}).get("city")
            if canonical:
                best_city = canonical
                best_len  = len(norm_key)

    return best_city


# ─── Niveau 3 — géolocalisation → ville la plus proche ───────────────────────

def _nearest_city_from_coords(lat: float, lng: float) -> Optional[str]:
    """
    Retourne la ville tunisienne la plus proche via AIRPORT_COORDS + haversine.
    None si hors de Tunisia (> MAX_GEOLOC_RADIUS_KM de tout aéroport).
    """
    from app.data.tunisia_destinations import AIRPORT_COORDS, TUNISIA_DESTINATIONS

    nearest_iata: Optional[str] = None
    min_dist: float = float("inf")

    for iata, (alat, alng) in AIRPORT_COORDS.items():
        dist = _haversine(lat, lng, alat, alng)
        if dist < min_dist:
            min_dist  = dist
            nearest_iata = iata

    if nearest_iata and min_dist <= MAX_GEOLOC_RADIUS_KM:
        city = TUNISIA_DESTINATIONS.get(nearest_iata, {}).get("city")
        logger.info(
            f"[AvailabilityService] géoloc ({lat:.4f},{lng:.4f}) → "
            f"{nearest_iata} — {city} ({min_dist:.0f} km)"
        )
        return city

    logger.warning(
        f"[AvailabilityService] géoloc ({lat:.4f},{lng:.4f}) hors Tunisie "
        f"(min_dist={min_dist:.0f} km)"
    )
    return None


# ─── Extraction destination hôtel (3 niveaux) ────────────────────────────────

def _extract_destination_from_hotel(
    hotel_info: Dict[str, Any],
    geolocation: Optional[Dict[str, Any]] = None,
) -> Optional[str]:
    """
    Niveau 1 : hotel.address dict — plusieurs noms de clés possibles.
    Niveau 2 : hotel.address string OU hotel.name → scan CITY_TO_IATA.
    Niveau 3 : geolocation (lat/lng) → ville la plus proche.
    """
    address = hotel_info.get("address")

    # ── Niveau 1 : address dict structuré ────────────────────────────
    if isinstance(address, dict):
        raw_city = (
            address.get("city")
            or address.get("ville")
            or address.get("locality")
            or address.get("municipality")
            or address.get("town")
            or address.get("region")
            or address.get("gouvernorat")
            or address.get("state")
        )
        if raw_city:
            matched = _match_city_in_text(str(raw_city))
            if matched:
                logger.debug(f"[AvailabilityService] destination (L1-dict): {matched}")
                return matched

    # ── Niveau 2a : address string libre ─────────────────────────────
    if isinstance(address, str) and address.strip():
        matched = _match_city_in_text(address)
        if matched:
            logger.debug(f"[AvailabilityService] destination (L2-address): {matched}")
            return matched

    # ── Niveau 2b : hotel name ────────────────────────────────────────
    hotel_name = hotel_info.get("name") or hotel_info.get("shortDescription") or ""
    if hotel_name:
        matched = _match_city_in_text(hotel_name)
        if matched:
            logger.debug(f"[AvailabilityService] destination (L2-name '{hotel_name}'): {matched}")
            return matched

    # ── Niveau 3 : géolocalisation ────────────────────────────────────
    if geolocation:
        lat = geolocation.get("lat") or geolocation.get("latitude")
        lng = geolocation.get("lng") or geolocation.get("longitude") or geolocation.get("lon")
        if lat is not None and lng is not None:
            city = _nearest_city_from_coords(float(lat), float(lng))
            if city:
                logger.debug(f"[AvailabilityService] destination (L3-geoloc): {city}")
                return city

    logger.warning(
        f"[AvailabilityService] destination introuvable — "
        f"hotel='{hotel_info.get('name')}' | address={address!r}"
    )
    return None


# ─── Fetch réservations voyageur ──────────────────────────────────────────────

def _parse_date(date_str: Optional[str]) -> Optional[date]:
    if not date_str:
        return None
    try:
        return datetime.fromisoformat(str(date_str)[:10]).date()
    except (ValueError, TypeError):
        return None


def get_traveller_bookings(traveller_id: str) -> List[Dict[str, Any]]:
    """
    Réservations actives du voyageur — cache TTL 1h.
    Essaie filtre serveur ?travellerId=, puis filtre client-side.
    """
    if not traveller_id:
        return []

    cache_key = f"traveller_bookings_{traveller_id}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    bookings: List[Dict[str, Any]] = []
    try:
        resp = requests.get(
            BOOKINGS_API_URL,
            headers=HEADERS,
            params={"travellerId": traveller_id, "take": 100},
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        results = resp.json().get("results", [])

        # Filtre client-side (au cas où le serveur ignore le param)
        bookings = [
            b for b in results
            if str(b.get("travellerId", "")) == str(traveller_id)
            and b.get("status") != "Cancelled"
        ]

        if not bookings and results:
            # Le serveur a déjà filtré → on garde tout
            bookings = [b for b in results if b.get("status") != "Cancelled"]

        if not results:
            # Serveur ignore le param → fetch complet + filtre
            resp2 = requests.get(
                BOOKINGS_API_URL,
                headers=HEADERS,
                params={"take": 200},
                timeout=TIMEOUT,
            )
            resp2.raise_for_status()
            all_b = resp2.json().get("results", [])
            bookings = [
                b for b in all_b
                if str(b.get("travellerId", "")) == str(traveller_id)
                and b.get("status") != "Cancelled"
            ]

    except Exception as e:
        logger.error(f"[AvailabilityService] get_traveller_bookings({traveller_id}): {e}")
        return []

    cache.set(cache_key, bookings, SimpleTTLCache.TTL_PROFILE)
    return bookings


# ─── Point d'entrée ───────────────────────────────────────────────────────────

def check_availability(
    traveller_id: Optional[str],
    profile_data: Optional[Dict[str, Any]],
    request_date: Optional[str] = None,
    geolocation: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Vérifie la disponibilité du voyageur.

    Args:
        traveller_id   : ID du voyageur (ou None pour USER NATIF)
        profile_data   : données profil depuis profile_loader_node
        request_date   : date ISO de référence (optionnel, défaut = aujourd'hui)
        geolocation    : {lat, lng} depuis le device (optionnel — niveau 3)

    Returns:
        {
            trip_is_ongoing, outbound_date, return_date, days_remaining,
            hotel_name, destination,
            booked_activity_ids, booked_time_slots,
            destination_source   # "address_dict"|"address_str"|"hotel_name"|"geolocation"|None
        }
    """
    result: Dict[str, Any] = {
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

    profile = profile_data or {}

    # ── Dates de voyage ───────────────────────────────────────────────
    outbound_dt = _parse_date(profile.get("outboundDate") or profile.get("outbound_date"))
    return_dt   = _parse_date(profile.get("returnDate")   or profile.get("return_date"))

    result["outbound_date"] = str(outbound_dt) if outbound_dt else None
    result["return_date"]   = str(return_dt)   if return_dt   else None

    today = _parse_date(request_date) or date.today()
    if outbound_dt and return_dt:
        result["trip_is_ongoing"] = outbound_dt <= today <= return_dt
        if result["trip_is_ongoing"]:
            result["days_remaining"] = (return_dt - today).days

    # ── Destination depuis hôtel (3 niveaux) ─────────────────────────
    accommodations = profile.get("accommodations") or []
    if accommodations:
        active = next(
            (a for a in accommodations if a.get("status") not in ("Cancelled",)),
            accommodations[0],
        )
        hotel_info = active.get("hotel") or {}
        result["hotel_name"] = hotel_info.get("name")

        # Détermination de la source pour traçabilité
        address = hotel_info.get("address")
        if isinstance(address, dict) and any(
            address.get(k) for k in ("city", "ville", "locality", "municipality", "town", "region", "gouvernorat", "state")
        ):
            source = "address_dict"
        elif isinstance(address, str) and address.strip():
            source = "address_str"
        elif hotel_info.get("name"):
            source = "hotel_name"
        elif geolocation:
            source = "geolocation"
        else:
            source = None

        destination = _extract_destination_from_hotel(hotel_info, geolocation)
        result["destination"]        = destination
        result["destination_source"] = source if destination else None

    elif geolocation:
        # Pas d'hôtel dans le profil → géoloc directe
        lat = geolocation.get("lat") or geolocation.get("latitude")
        lng = geolocation.get("lng") or geolocation.get("longitude") or geolocation.get("lon")
        if lat is not None and lng is not None:
            result["destination"]        = _nearest_city_from_coords(float(lat), float(lng))
            result["destination_source"] = "geolocation"

    # ── Réservations d'activités existantes ──────────────────────────
    if traveller_id:
        bookings = get_traveller_bookings(str(traveller_id))
        booked_ids: Set[str] = set()
        time_slots: List[Dict[str, Any]] = []
        for b in bookings:
            act_id = b.get("activityId")
            if act_id:
                booked_ids.add(str(act_id))
                b_date = b.get("date")
                if b_date:
                    time_slots.append({
                        "activity_id": str(act_id),
                        "date":        b_date,
                        "status":      b.get("status"),
                    })
        result["booked_activity_ids"] = list(booked_ids)
        result["booked_time_slots"]   = time_slots

    logger.info(
        f"[AvailabilityService] trip_is_ongoing={result['trip_is_ongoing']} | "
        f"destination={result['destination']!r} (source={result['destination_source']}) | "
        f"hotel={result['hotel_name']!r}"
    )
    return result
