"""
AvailabilityService — Vérification disponibilité voyageur
==========================================================
Détermine la destination réelle via 3 niveaux de fallback :
  Niveau 3 — géolocalisation GPS → ville tunisienne la plus proche

Source : GET /api/bookings?travellerId={id}
"""
import logging
import math
import re
import requests
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Set, Tuple

from app.config.settings import BOOKINGS_API_URL, API_KEY
from app.services.cache_service import SimpleTTLCache, cache
from app.utils.text_utils import normalize_text as _normalize

logger = logging.getLogger(__name__)

HEADERS  = {"Authorization": f"Bearer {API_KEY}"}
TIMEOUT  = 15
MAX_GEOLOC_RADIUS_KM = 200   # au-delà → pas de correspondance


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


# Texte désignant le pays entier, jamais une ville/région précise — sert à
# context_merger_node pour éviter de traiter "Tunisie"/"Tunisia" comme une
# destination résolue quand _match_city_in_text ne reconnaît aucune ville
# (sinon le fallback "garder le texte brut" du context_merger repasserait
# silencieusement le nom du pays comme si c'était une destination valide).
_COUNTRY_LEVEL_DESTINATIONS = {"tunisie", "tunisia"}


def is_country_level_destination(text: str) -> bool:
    """True si le texte désigne le pays entier (pas une ville/région précise)."""
    return _normalize(text).strip() in _COUNTRY_LEVEL_DESTINATIONS


# ─── Niveau 2 — scan texte → ville connue ────────────────────────────────────

def _match_city_in_text(text: str) -> Optional[str]:
    """
    Cherche un nom de ville tunisienne connu dans un texte libre.
    Retourne le nom canonique (ex: "Sousse", "Hammamet / Nabeul").
    Prend le match le plus long pour éviter "el" dans "el kantaoui".

    Matching sur limites de mot (\\b) — pas un simple containment substring :
    "tunis" ne doit PAS matcher dans "tunisie" (le pays entier, pas la ville),
    bug trouvé en testant le mode exploratoire ("je veux organiser un voyage
    en Tunisie" était silencieusement résolu en destination="Tunis", cachant
    le besoin réel de clarification sur la région/ville).
    """
    from app.data.tunisia_destinations import CITY_TO_IATA, TUNISIA_DESTINATIONS

    normalized_text = _normalize(text)
    best_city: Optional[str] = None
    best_len: int = 0

    for city_key, iata in CITY_TO_IATA.items():
        norm_key = _normalize(city_key)
        if len(norm_key) < 3:          # ignorer clés trop courtes ("el", "le")
            continue
        pattern = r"\b" + re.escape(norm_key) + r"\b"
        if re.search(pattern, normalized_text) and len(norm_key) > best_len:
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



# ─── Fetch réservations voyageur ──────────────────────────────────────────────

def _parse_date(date_str: Optional[str]) -> Optional[date]:
    """
    Convertit une string ISO (API / profile / intent)
    en objet date robuste.
    """

    if not date_str:
        return None

    try:
        s = str(date_str).strip()

        # ── Cas ISO Z (UTC) ─────────────────────────
        # 2026-06-24T10:30:00Z
        if s.endswith("Z"):
            s = s.replace("Z", "+00:00")

        # ── datetime ISO standard ───────────────────
        dt = datetime.fromisoformat(s)

        return dt.date()

    except Exception:
        try:
            # fallback ultra simple (YYYY-MM-DD)
            return datetime.strptime(s[:10], "%Y-%m-%d").date()
        except Exception:
            return None


# ─── Ancres booking (ce que le voyageur a déjà payé) ─────────────────────────

def _normalize_meal_plan(meal_plan: Optional[str]) -> Dict[str, Any]:
    """
    Dérive les repas inclus depuis le libellé du contrat.
    Conventions : RO=logement seul | BB=petit-déj | HB=petit-déj+dîner
                  FB=pension complète | AI=all inclusive
    Libellé inconnu → tout None (on ne devine jamais).
    """
    flags = {"breakfast_included": None, "lunch_included": None, "dinner_included": None}
    if not meal_plan:
        return flags

    mp = _normalize(meal_plan)
    if "all" in mp or mp in ("ai", "ultra"):
        return {"breakfast_included": True, "lunch_included": True, "dinner_included": True}
    if "full" in mp or "complete" in mp or mp == "fb":
        return {"breakfast_included": True, "lunch_included": True, "dinner_included": True}
    if "half" in mp or "demi" in mp or mp == "hb":
        return {"breakfast_included": True, "lunch_included": False, "dinner_included": True}
    if "breakfast" in mp or "petit" in mp or mp == "bb":
        return {"breakfast_included": True, "lunch_included": False, "dinner_included": False}
    if "room" in mp or "logement" in mp or mp == "ro":
        return {"breakfast_included": False, "lunch_included": False, "dinner_included": False}
    return flags


def _build_booking_anchors(profile: Dict[str, Any]) -> Dict[str, Any]:
    """
    Consolide ce que le voyageur a DÉJÀ payé — les ancres immuables
    autour desquelles toute journée doit être planifiée.
    Lecture pure de profile_data (chargé depuis Redis) — aucun appel API.
    """
    prefs         = profile.get("travel_preferences") or {}
    accommodation = prefs.get("accommodation") or {}
    transfer      = prefs.get("transfer") or {}

    meal_plan = accommodation.get("meal_plan")
    anchors = {
        "meal_plan":       meal_plan,
        **_normalize_meal_plan(meal_plan),
        "hotel_name":      accommodation.get("hotel_name"),
        "hotel_zone":      accommodation.get("hotel_zone"),
        "booked_services": accommodation.get("booked_services") or [],
        "transfer":        transfer or None,
    }
    return anchors


# ─── Position dans le séjour ──────────────────────────────────────────────────

def _build_trip_position(
    outbound_dt: Optional[date],
    return_dt: Optional[date],
    today: date,
    profile: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Position temporelle du voyageur dans son séjour.
    day_index=1 = jour d'arrivée. Tout est None/False si pas de voyage en cours.
    arrival_time / departure_time proviennent des vols du travel plan —
    ils définissent la fenêtre horaire utile du premier et du dernier jour.
    """
    position = {
        "day_index":      None,
        "total_days":     None,
        "is_first_day":   False,
        "is_last_day":    False,
        "arrival_time":   None,
        "departure_time": None,
    }

    if not (outbound_dt and return_dt and outbound_dt <= today <= return_dt):
        return position

    position["day_index"]    = (today - outbound_dt).days + 1
    position["total_days"]   = (return_dt - outbound_dt).days + 1
    position["is_first_day"] = today == outbound_dt
    position["is_last_day"]  = today == return_dt

    flights  = (profile.get("travel_preferences") or {}).get("flights") or {}
    outbound = flights.get("outbound") or {}
    ret      = flights.get("return")   or {}
    position["arrival_time"]   = outbound.get("landing_time")
    position["departure_time"] = ret.get("takeoff_time")

    return position


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
    context_merge: Optional[Dict[str, Any]] = None,
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
        "trip_position":       None,
        "booking_anchors":     None,
        "hotel_name":          None,
        "destination":         None,
        "destination_source":  None,
        "booked_activity_ids": [],
        "booked_time_slots":   [],
    }

    profile = profile_data or {}
    availability = profile.get("availability") or {}

    # ── Dates de voyage ───────────────────────────────────────────────
    outbound_dt = _parse_date(availability.get("outbound_date"))
    return_dt   = _parse_date(availability.get("return_date"))

    result["outbound_date"] = str(outbound_dt) if outbound_dt else None
    result["return_date"]   = str(return_dt)   if return_dt   else None

    today = _parse_date(request_date) or date.today()
    if outbound_dt and return_dt:
        result["trip_is_ongoing"] = outbound_dt <= today <= return_dt
        if result["trip_is_ongoing"]:
            result["days_remaining"] = (return_dt - today).days

    result["trip_position"]   = _build_trip_position(outbound_dt, return_dt, today, profile)
    result["booking_anchors"] = _build_booking_anchors(profile)


    destination = (context_merge or {}).get("destination")

    if destination:
        result["destination"] = destination
        result["destination_source"] = (context_merge or {}).get("destination_source", "context_merge")

    # ── 3. FALLBACK ULTRA BAS NIVEAU (UNIQUEMENT SI BUG) ─────
    elif geolocation:
        lat = geolocation.get("lat") or geolocation.get("latitude")
        lng = geolocation.get("lng") or geolocation.get("longitude") or geolocation.get("lon")

        if lat is not None and lng is not None:
            result["destination"] = _nearest_city_from_coords(float(lat), float(lng))
            result["destination_source"] = "geolocation_fallback"
            
            

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
