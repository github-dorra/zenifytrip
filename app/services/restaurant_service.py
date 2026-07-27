"""
Restaurant Service — Production

Tier 1 : MongoDB RestaurantGuru  — recherche par city + zone + destination (zéro coût API)
Tier 2 : Google Places API       — fallback si MongoDB < MONGO_MIN_RESULTS résultats

Décision architecturale (2026-06-08) :
  Approche A (Google Places) retenue pour les données vérifiées.
  MongoDB ajouté en Tier 1 (2026-07-04) pour couvrir les villes tunisiennes scrapées.
"""

import logging
from typing import Dict, Any, List, Optional, Tuple

from app.config.settings import RESTAURANT_MONGO_MIN_RESULTS
from app.services.restaurant_service_a import RestaurantServiceA
from app.services.mongo_restaurant_service import MongoRestaurantService

logger = logging.getLogger(__name__)

# Seuil minimum de résultats MongoDB pour éviter le fallback Google Places
MONGO_MIN_RESULTS = RESTAURANT_MONGO_MIN_RESULTS


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
        benchmark["tier_used"] = "google_places" if not mongo_results else "mixed"

        google_results, google_bench = RestaurantServiceA.get_restaurant_candidates(
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
