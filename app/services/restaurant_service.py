"""
Restaurant Service — Production

Tier 1 : MongoDB RestaurantGuru  — recherche par city + zone + destination (zéro coût API)
Tier 2 : Google Places API       — fallback si MongoDB < MONGO_MIN_RESULTS résultats

Décision architecturale (2026-06-08) :
  Approche A (Google Places) retenue pour les données vérifiées.
  MongoDB ajouté en Tier 1 (2026-07-04) pour couvrir les villes tunisiennes scrapées.
"""

import hashlib
import json
import logging
import time
from typing import Dict, Any, List, Optional, Tuple

import requests

from app.config.settings import RESTAURANT_MONGO_MIN_RESULTS, RESTAURANT_TIER2_PROVIDER, SERPAPI_KEY
from app.services.cache_service import cache, SimpleTTLCache
from app.services.restaurant_service_a import RestaurantServiceA
from app.services.mongo_restaurant_service import MongoRestaurantService

logger = logging.getLogger(__name__)

# Seuil minimum de résultats MongoDB pour éviter le fallback Google Places
MONGO_MIN_RESULTS = RESTAURANT_MONGO_MIN_RESULTS

SERPAPI_BASE = "https://serpapi.com/search"
_SKIP_TYPES  = {"restaurant", "food", "point_of_interest", "establishment", "store"}


class RestaurantServiceSerpApi:
    """
    Tier 2 temporaire — remplace Google Places (bloqué : REQUEST_DENIED,
    facturation Google Cloud non activée). SerpApi (moteur google_maps)
    retourne les mêmes données structurées sans dépendre de ce compte —
    déjà validé pour la Tunisie lors du backfill des zones sous-couvertes
    (session 2026-07-23).

    Même interface que RestaurantServiceA.get_restaurant_candidates() pour
    un remplacement transparent. Réutilise RestaurantServiceA.score() tel
    quel — même logique de scoring, pas de duplication.
    """

    TIMEOUT = 10
    TTL = SimpleTTLCache.TTL_RESTAURANTS

    @staticmethod
    def _cache_key(prefix: str, **kwargs) -> str:
        raw = json.dumps(kwargs, sort_keys=True, ensure_ascii=False)
        h = hashlib.md5(raw.encode()).hexdigest()[:10]
        return f"{prefix}_{h}"

    @staticmethod
    def _parse_result(place: Dict, lat_ref: Optional[float], lng_ref: Optional[float]) -> Dict:
        gps = place.get("gps_coordinates") or {}
        lat = gps.get("latitude")
        lng = gps.get("longitude")

        distance_km = None
        if lat and lng and lat_ref is not None and lng_ref is not None:
            distance_km = RestaurantServiceA._compute_distance(lat_ref, lng_ref, lat, lng)

        price_str = place.get("price")
        price_level = price_str.count("$") if price_str else None

        raw_types = place.get("type") or place.get("types") or []
        if isinstance(raw_types, str):
            raw_types = [raw_types]
        cuisine_types = [t for t in raw_types if t not in _SKIP_TYPES]

        return {
            "id":                 place.get("place_id") or place.get("data_id") or "",
            "name":               place.get("title") or "",
            "description":        place.get("address") or place.get("type"),
            "address":            place.get("address"),
            "lat":                lat,
            "lng":                lng,
            "rating":             place.get("rating"),
            "user_ratings_total": place.get("reviews"),
            "price_level":        price_level,
            "cuisine_types":      cuisine_types,
            "is_open_now":        None,  # SerpApi expose des horaires texte, pas de booleen fiable
            "distance_km":        distance_km,
            "photo_reference":    place.get("thumbnail"),
            "match_score":        0.0,
            "matched_criteria":   [],
            "tier":               "serpapi",
            "source":             "serpapi",
        }

    @staticmethod
    def _search(query: str, lat: Optional[float], lng: Optional[float],
                max_results: int) -> Tuple[List[Dict], int]:
        cache_key = RestaurantServiceSerpApi._cache_key(
            "rest_serpapi", q=query, lat=round(lat, 3) if lat else None,
            lng=round(lng, 3) if lng else None,
        )
        cached = cache.get(cache_key)
        if cached is not None:
            logger.info(f"RestaurantServiceSerpApi: cache HIT [{cache_key}]")
            return cached, 0

        if not SERPAPI_KEY:
            logger.error("RestaurantServiceSerpApi: SERPAPI_KEY manquant dans .env")
            return [], 0

        params = {"engine": "google_maps", "q": query, "type": "search", "api_key": SERPAPI_KEY}
        if lat is not None and lng is not None:
            params["ll"] = f"@{lat},{lng},14z"

        try:
            resp = requests.get(SERPAPI_BASE, params=params, timeout=RestaurantServiceSerpApi.TIMEOUT)
            resp.raise_for_status()
            payload = resp.json()

            if "error" in payload:
                logger.error(f"RestaurantServiceSerpApi error: {payload['error']}")
                return [], 1

            raw_results = payload.get("local_results", [])[:max_results]
            parsed = [RestaurantServiceSerpApi._parse_result(p, lat, lng) for p in raw_results]
            cache.set(cache_key, parsed, RestaurantServiceSerpApi.TTL)
            return parsed, 1

        except Exception as e:
            logger.error(f"RestaurantServiceSerpApi._search [{query}]: {e}")
            return [], 1

    @staticmethod
    def get_restaurant_candidates(
        semantic_query: str,
        global_keywords: List[str],
        destination: Optional[str],
        budget_level: Optional[str],
        is_family: bool,
        search_strategy: Dict,
        max_candidates: int = 10,
    ) -> Tuple[List[Dict], Dict]:
        mode = search_strategy.get("mode", "exploratory")
        reference_coords = search_strategy.get("reference_coords")
        require_diversity = search_strategy.get("require_diversity", False)

        benchmark = {
            "api_calls_google": 0,  # nom conserve pour compatibilite avec le benchmark existant
            "cache_hits": 0,
            "search_mode": mode,
            "latency_api_ms": 0,
        }

        lat, lng = (reference_coords if reference_coords else (None, None))
        query = semantic_query or f"restaurants {destination or 'tunisie'}"

        t0 = time.time()
        raw, calls = RestaurantServiceSerpApi._search(query, lat, lng, max_candidates)
        benchmark["latency_api_ms"] = int((time.time() - t0) * 1000)
        benchmark["api_calls_google"] = calls
        if calls == 0:
            benchmark["cache_hits"] += 1

        # Reutilise RestaurantServiceA.score() tel quel — memes champs, pas de duplication
        for candidate in raw:
            sc, crit = RestaurantServiceA.score(candidate, global_keywords, budget_level, is_family)
            candidate["match_score"] = sc
            candidate["matched_criteria"] = crit

        raw.sort(key=lambda x: x["match_score"], reverse=True)

        if require_diversity:
            top = RestaurantServiceA._apply_diversity(raw, max_candidates)
        else:
            top = raw[:max_candidates]

        return top, benchmark


# Fournisseur Tier 2 — bascule via RESTAURANT_TIER2_PROVIDER (settings.py)
_TIER2_PROVIDERS = {
    "google_places": RestaurantServiceA,
    "serpapi":       RestaurantServiceSerpApi,
}


class RestaurantService(RestaurantServiceA):
    """
    Point d'entrée production.

    Priorité :
      1. MongoDB RestaurantGuru  (city / zone / destination)
      2. Google Places API        (fallback si Tier 1 insuffisant)
    """

    @staticmethod
    def get_restaurant_candidates(
        semantic_query:  str,
        global_keywords: List[str],
        destination:     Optional[str],
        budget_level:    Optional[str],
        is_family:       bool,
        search_strategy: Dict,
        max_candidates:  int = 10,
        halal_required:  bool = False,
    ) -> Tuple[List[Dict], Dict]:
        """
        Tier 1 — MongoDB (city + zone + destination).
        Tier 2 — Google Places si Tier 1 < MONGO_MIN_RESULTS résultats.
        """
        benchmark = {
            "api_calls_google": 0,
            "cache_hits":       0,
            "search_mode":      search_strategy.get("mode", "exploratory"),
            "latency_api_ms":   0,
            "mongo_results":    0,
            "tier_used":        "mongodb",
        }

        # ── Tier 1 : MongoDB ─────────────────────────────────────────────
        ref_coords = search_strategy.get("reference_coords")
        ref_lat, ref_lng = (ref_coords if ref_coords else (None, None))

        mongo_results = MongoRestaurantService.search(
            destination=destination,
            keywords=global_keywords,
            budget_level=budget_level,
            is_family=is_family,
            ref_lat=ref_lat,
            ref_lng=ref_lng,
            max_results=max_candidates,
            establishment_types=search_strategy.get("establishment_types"),
            halal_required=halal_required,
        )
        benchmark["mongo_results"] = len(mongo_results)

        if len(mongo_results) >= MONGO_MIN_RESULTS:
            logger.info(
                f"RestaurantService Tier1: MongoDB {len(mongo_results)} results "
                f"for destination='{destination}'"
            )
            return mongo_results, benchmark

        # ── Tier 2 : Google Places (fallback) ────────────────────────────
        logger.info(
            f"RestaurantService: MongoDB {len(mongo_results)} < {MONGO_MIN_RESULTS} "
            f"pour '{destination}' → Google Places fallback"
        )
        tier2 = _TIER2_PROVIDERS.get(RESTAURANT_TIER2_PROVIDER, RestaurantServiceA)
        benchmark["tier_used"] = f"{RESTAURANT_TIER2_PROVIDER}" if not mongo_results else "mixed"

        google_results, google_bench = tier2.get_restaurant_candidates(
            semantic_query=semantic_query,
            global_keywords=global_keywords,
            destination=destination,
            budget_level=budget_level,
            is_family=is_family,
            search_strategy=search_strategy,
            max_candidates=max_candidates,
        )
        benchmark["api_calls_google"] = google_bench.get("api_calls_google", 0)
        benchmark["cache_hits"]       = google_bench.get("cache_hits",       0)
        benchmark["latency_api_ms"]   = google_bench.get("latency_api_ms",   0)

        # Merge MongoDB + Google (MongoDB en premier — business_score plus élevé)
        merged = mongo_results + google_results
        merged.sort(key=lambda x: x.get("match_score", 0), reverse=True)
        return merged[:max_candidates], benchmark
