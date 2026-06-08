import math
import hashlib
import json
import logging
import requests
import time
from typing import Dict, Any, List, Optional, Tuple

from app.config.settings import GOOGLE_MAPS_API_KEY
from app.services.cache_service import cache, SimpleTTLCache

# URL fixe Google Places API — indépendante de GOOGLE_MAPS_BASE_URL (.env mal configuré)
PLACES_API_BASE = "https://maps.googleapis.com/maps/api"

logger = logging.getLogger(__name__)


class RestaurantServiceA:

    TIMEOUT = 10
    TTL     = SimpleTTLCache.TTL_RESTAURANTS  # 259200s = 72h

    BUDGET_TO_PRICE_LEVEL: Dict[str, Tuple[int, int]] = {
        "low":     (0, 1),
        "medium":  (1, 2),
        "luxury":  (3, 4),
        "premium": (3, 4),
    }

    # ------------------------------------------------------------------
    # Hotel coords — lookup dans HotelService cache (0 appel API si déjà en cache)
    # ------------------------------------------------------------------

    @staticmethod
    def get_hotel_coords(hotel_id: Optional[str]) -> Optional[Tuple[float, float]]:
        if not hotel_id:
            return None
        try:
            from app.services.hotel_service import HotelService

            # Tier 1 : partenaires (souvent déjà en cache)
            partner_hotels, _ = HotelService.get_partner_hotels()
            for hotel in partner_hotels:
                if str(hotel.get("id", "")) == str(hotel_id):
                    coords = RestaurantServiceA._parse_raw_coords(hotel.get("coordinates"))
                    if coords:
                        return coords

            # Tier 2 : catalogue complet
            all_hotels = HotelService.get_all_hotels()
            for hotel in all_hotels:
                if str(hotel.get("id", "")) == str(hotel_id):
                    coords = RestaurantServiceA._parse_raw_coords(hotel.get("coordinates"))
                    if coords:
                        return coords

        except Exception as e:
            logger.warning(f"RestaurantServiceA.get_hotel_coords: {e}")
        return None

    @staticmethod
    def _parse_raw_coords(raw: Any) -> Optional[Tuple[float, float]]:
        try:
            if not raw or not isinstance(raw, dict):
                return None
            coords = raw.get("coordinates", [])
            if isinstance(coords, list) and len(coords) == 2:
                return (float(coords[0]), float(coords[1]))
        except Exception:
            pass
        return None

    # ------------------------------------------------------------------
    # Haversine distance en km
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_distance(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
        R = 6371.0
        p1, p2 = math.radians(lat1), math.radians(lat2)
        dp = math.radians(lat2 - lat1)
        dl = math.radians(lng2 - lng1)
        a  = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
        return round(R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a)), 2)

    # ------------------------------------------------------------------
    # Clé cache stable
    # ------------------------------------------------------------------

    @staticmethod
    def _cache_key(prefix: str, **kwargs) -> str:
        raw = json.dumps(kwargs, sort_keys=True, ensure_ascii=False)
        h   = hashlib.md5(raw.encode()).hexdigest()[:10]
        return f"{prefix}_{h}"

    # ------------------------------------------------------------------
    # Parse un résultat Google Places → dict normalisé
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_place(
        place: Dict,
        lat_ref: Optional[float],
        lng_ref: Optional[float],
        tier: str,
    ) -> Dict:
        geometry = place.get("geometry") or {}
        location = geometry.get("location") or {}
        lat = location.get("lat")
        lng = location.get("lng")

        distance_km = None
        if lat and lng and lat_ref is not None and lng_ref is not None:
            distance_km = RestaurantServiceA._compute_distance(lat_ref, lng_ref, lat, lng)

        # description : editorial_summary > vicinity > formatted_address
        description = (
            (place.get("editorial_summary") or {}).get("overview")
            or place.get("vicinity")
            or place.get("formatted_address")
            or None
        )

        opening = place.get("opening_hours") or {}
        is_open = opening.get("open_now")

        photos   = place.get("photos") or []
        photo_ref = photos[0].get("photo_reference") if photos else None

        # Filtrer les types génériques Google
        skip = {"restaurant", "food", "point_of_interest", "establishment", "store"}
        cuisine_types = [t for t in (place.get("types") or []) if t not in skip]

        return {
            "id":                 place.get("place_id") or "",
            "name":               place.get("name") or "",
            "description":        description,
            "address":            place.get("vicinity") or place.get("formatted_address"),
            "lat":                lat,
            "lng":                lng,
            "rating":             place.get("rating"),
            "user_ratings_total": place.get("user_ratings_total"),
            "price_level":        place.get("price_level"),
            "cuisine_types":      cuisine_types,
            "is_open_now":        is_open,
            "distance_km":        distance_km,
            "photo_reference":    photo_ref,
            "match_score":        0.0,
            "matched_criteria":   [],
            "tier":               tier,
            "source":             "google_places",
        }

    # ------------------------------------------------------------------
    # Nearby Search — autour des coordonnées de l'hôtel
    # ------------------------------------------------------------------

    @staticmethod
    def search_nearby(
        lat: float,
        lng: float,
        semantic_query: str,
        radius_m: int = 2000,
        max_results: int = 10,
    ) -> Tuple[List[Dict], int]:
        """Retourne (candidats, nb_appels_api)."""
        cache_key = RestaurantServiceA._cache_key(
            "rest_nearby",
            lat=round(lat, 3), lng=round(lng, 3),
            radius=radius_m, q=semantic_query,
        )
        cached = cache.get(cache_key)
        if cached is not None:
            logger.info(f"RestaurantServiceA: nearby cache HIT [{cache_key}]")
            return cached, 0

        try:
            url    = f"{PLACES_API_BASE}/place/nearbysearch/json"
            params = {
                "location": f"{lat},{lng}",
                "radius":   radius_m,
                "type":     "restaurant",
                "keyword":  semantic_query,
                "key":      GOOGLE_MAPS_API_KEY,
            }
            resp = requests.get(url, params=params, timeout=RestaurantServiceA.TIMEOUT)
            resp.raise_for_status()
            raw_results = resp.json().get("results", [])[:max_results]

            parsed = [
                RestaurantServiceA._parse_place(p, lat, lng, "nearby")
                for p in raw_results
            ]
            cache.set(cache_key, parsed, RestaurantServiceA.TTL)
            return parsed, 1

        except Exception as e:
            logger.error(f"RestaurantServiceA.search_nearby: {e}")
            return [], 1

    # ------------------------------------------------------------------
    # Text Search — par requête sémantique
    # ------------------------------------------------------------------

    @staticmethod
    def search_by_text(
        semantic_query: str,
        max_results: int = 10,
    ) -> Tuple[List[Dict], int]:
        """Retourne (candidats, nb_appels_api)."""
        cache_key = RestaurantServiceA._cache_key("rest_text", q=semantic_query)
        cached = cache.get(cache_key)
        if cached is not None:
            logger.info(f"RestaurantServiceA: text cache HIT [{cache_key}]")
            return cached, 0

        try:
            url    = f"{PLACES_API_BASE}/place/textsearch/json"
            params = {
                "query": semantic_query,
                "type":  "restaurant",
                "key":   GOOGLE_MAPS_API_KEY,
            }
            resp = requests.get(url, params=params, timeout=RestaurantServiceA.TIMEOUT)
            resp.raise_for_status()
            raw_results = resp.json().get("results", [])[:max_results]

            parsed = [
                RestaurantServiceA._parse_place(p, None, None, "text_search")
                for p in raw_results
            ]
            cache.set(cache_key, parsed, RestaurantServiceA.TTL)
            return parsed, 1

        except Exception as e:
            logger.error(f"RestaurantServiceA.search_by_text: {e}")
            return [], 1

    # ------------------------------------------------------------------
    # Scoring — 0.0 → 1.0
    # ------------------------------------------------------------------

    @staticmethod
    def score(
        candidate: Dict,
        global_keywords: List[str],
        budget_level: Optional[str],
        is_family: bool,
    ) -> Tuple[float, List[str]]:
        s        = 0.0
        criteria = []

        # Rating (max 0.30)
        rating = candidate.get("rating") or 0.0
        if rating >= 4.5:
            s += 0.30; criteria.append("rating_excellent")
        elif rating >= 4.0:
            s += 0.20; criteria.append("rating_good")
        elif rating >= 3.5:
            s += 0.10; criteria.append("rating_ok")

        # Open now (0.20)
        if candidate.get("is_open_now") is True:
            s += 0.20; criteria.append("open_now")

        # Budget → price_level (0.20)
        price_level = candidate.get("price_level")
        if price_level is not None and budget_level:
            lo, hi = RestaurantServiceA.BUDGET_TO_PRICE_LEVEL.get(budget_level, (0, 4))
            if lo <= price_level <= hi:
                s += 0.20; criteria.append("budget_match")

        # Keyword match via name + description + cuisine_types (0.20)
        if global_keywords:
            text = " ".join(filter(None, [
                (candidate.get("name") or "").lower(),
                (candidate.get("description") or "").lower(),
                " ".join(candidate.get("cuisine_types") or []).lower(),
            ]))
            # Extraire la partie significative du keyword (ex: "seafoodRestaurant" → "seafood")
            matched = []
            for kw in global_keywords:
                stem = kw.lower()
                for suffix in ("restaurant", "dining", "food", "cuisine", "cafe", "eating"):
                    stem = stem.replace(suffix, "")
                stem = stem.strip()
                if stem and stem in text:
                    matched.append(kw)
            if matched:
                ratio = len(matched) / len(global_keywords)
                s += round(min(0.20, ratio * 0.20), 4)
                criteria.append("keyword_match")

        # Bonus famille (0.10)
        if is_family and any(kw in global_keywords for kw in ("familyRestaurant", "familyDining", "foodCourt")):
            s += 0.10; criteria.append("family_match")

        return round(min(s, 1.0), 4), criteria

    # ------------------------------------------------------------------
    # Place Details — enrichissement d'un candidat via place_id
    # ------------------------------------------------------------------

    DETAILS_FIELDS = ",".join([
        "formatted_phone_number",
        "website",
        "opening_hours",
        "serves_lunch",
        "serves_dinner",
        "serves_breakfast",
        "dine_in",
        "takeout",
        "delivery",
        "reservable",
        "serves_vegetarian_food",
        "serves_beer",
        "serves_wine",
        "reviews",
        "price_level",
        # "payment_options" retiré — champ Places API (New) uniquement, cause INVALID_REQUEST sur l'API legacy
    ])

    @staticmethod
    def get_place_details(place_id: str) -> Optional[Dict]:
        """Récupère les détails complets d'un lieu via son place_id — mis en cache 72h."""
        if not place_id or place_id.startswith("llm_") or place_id.startswith("tavily_"):
            return None

        cache_key = f"place_details_{place_id}"
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

        try:
            url = f"{PLACES_API_BASE}/place/details/json"
            params = {
                "place_id": place_id,
                "fields":   RestaurantServiceA.DETAILS_FIELDS,
                "key":      GOOGLE_MAPS_API_KEY,
            }
            resp = requests.get(url, params=params, timeout=RestaurantServiceA.TIMEOUT)
            resp.raise_for_status()
            result = resp.json().get("result") or {}
            if result:
                cache.set(cache_key, result, SimpleTTLCache.TTL_RESTAURANTS)
            return result
        except Exception as e:
            logger.warning(f"RestaurantServiceA.get_place_details [{place_id}]: {e}")
            return None

    @staticmethod
    def _format_place_details(details: Dict) -> Optional[str]:
        """Formate les details Place Details en texte ASCII pour le ranking LLM."""
        if not details:
            return None

        lines = []

        # Services
        services = []
        if details.get("dine_in")    is True: services.append("sur place")
        if details.get("takeout")    is True: services.append("a emporter")
        if details.get("delivery")   is True: services.append("livraison")
        if details.get("reservable") is True: services.append("reservation possible")
        if services:
            lines.append("Service: " + ", ".join(services))

        # Repas servis
        meals = []
        if details.get("serves_breakfast") is True: meals.append("petit-dejeuner")
        if details.get("serves_lunch")     is True: meals.append("dejeuner")
        if details.get("serves_dinner")    is True: meals.append("diner")
        if meals:
            lines.append("Repas: " + ", ".join(meals))

        # Options alimentaires
        opts = []
        if details.get("serves_vegetarian_food") is True: opts.append("vegetarien")
        if details.get("serves_beer")            is True: opts.append("biere")
        if details.get("serves_wine")            is True: opts.append("vin")
        if opts:
            lines.append("Options: " + ", ".join(opts))

        # Horaires (3 premiers jours)
        opening = details.get("opening_hours") or {}
        weekday = opening.get("weekday_text") or []
        if weekday:
            lines.append("Horaires: " + " | ".join(weekday[:3]))

        # Contact
        phone = details.get("formatted_phone_number")
        if phone:
            lines.append("Tel: " + phone)

        website = details.get("website")
        if website:
            domain = website.split("//")[-1].split("/")[0]
            lines.append("Site: " + domain)

        # Meilleur avis client
        reviews = details.get("reviews") or []
        if reviews:
            best = max(reviews, key=lambda r: r.get("rating", 0))
            text = (best.get("text") or "").replace("\n", " ")[:150]
            rating = best.get("rating", "")
            if text:
                lines.append(f"Meilleur avis ({rating}/5): {text}")

        return "\n".join(lines) if lines else None

    # ------------------------------------------------------------------
    # Point d'entrée principal — Tier 1 Nearby → Tier 2 Text Search
    # ------------------------------------------------------------------

    @staticmethod
    def get_restaurant_candidates(
        semantic_query: str,
        global_keywords: List[str],
        destination: Optional[str],
        budget_level: Optional[str],
        is_family: bool,
        hotel_id: Optional[str],
        suggestion_mode: str,
        max_candidates: int = 10,
    ) -> Tuple[List[Dict], Dict]:
        """
        Tier 1 : Nearby Search si coords hôtel disponibles (USER RÉEL)
        Tier 2 : Text Search sinon (USER NATIF ou fallback)

        Retourne (candidats_scorés, benchmark_dict).
        """
        benchmark = {
            "api_calls_google": 0,
            "cache_hits":       0,
            "search_mode":      "none",
            "latency_api_ms":   0,
        }

        raw: List[Dict] = []

        # ── TIER 1 — Nearby Search ────────────────────────────────────
        coords = RestaurantServiceA.get_hotel_coords(hotel_id)
        if coords:
            lat, lng = coords

            t0 = time.time()
            results, calls = RestaurantServiceA.search_nearby(
                lat, lng, semantic_query, radius_m=2000, max_results=max_candidates,
            )
            benchmark["latency_api_ms"] += int((time.time() - t0) * 1000)
            benchmark["api_calls_google"] += calls
            if calls == 0:
                benchmark["cache_hits"] += 1

            # Élargir à 5km si moins de 3 résultats
            if len(results) < 3:
                t0 = time.time()
                results, calls = RestaurantServiceA.search_nearby(
                    lat, lng, semantic_query, radius_m=5000, max_results=max_candidates,
                )
                benchmark["latency_api_ms"] += int((time.time() - t0) * 1000)
                benchmark["api_calls_google"] += calls
                if calls == 0:
                    benchmark["cache_hits"] += 1

            raw         = results
            benchmark["search_mode"] = "nearby"

        # ── TIER 2 — Text Search ──────────────────────────────────────
        if not raw:
            query = semantic_query or f"restaurants {destination or 'tunisie'}"
            t0 = time.time()
            results, calls = RestaurantServiceA.search_by_text(query, max_results=max_candidates)
            benchmark["latency_api_ms"] += int((time.time() - t0) * 1000)
            benchmark["api_calls_google"] += calls
            if calls == 0:
                benchmark["cache_hits"] += 1
            raw                      = results
            benchmark["search_mode"] = "text_search"

        # ── Score + tri ───────────────────────────────────────────────
        for candidate in raw:
            sc, crit = RestaurantServiceA.score(
                candidate, global_keywords, budget_level, is_family,
            )
            candidate["match_score"]      = sc
            candidate["matched_criteria"] = crit

        raw.sort(key=lambda x: x["match_score"], reverse=True)
        top = raw[:max_candidates]

        return top, benchmark
