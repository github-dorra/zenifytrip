"""
MongoRestaurantService — Tier 1 source pour les candidats restaurants.

Recherche dans restaurant_collection (données RestaurantGuru scrapées) par :
  1. city  — correspondance exacte (insensible à la casse)
  2. zone  — correspondance partielle sur le gouvernorat (ex: "Sousse" dans "Gouvernorat de Sousse")

business_score = 0.6 par défaut (données propres, zéro coût API, source vérifiée) ;
priorité à la valeur explicite du document si présente (ex. 0.20 pour les
établissements enrichis via SerpApi/Google — cf. scrape_zone_serpapi.py).
Fallback Google Places (RestaurantServiceA) si résultats < seuil.
"""

import logging
import math
import re
from typing import Dict, Any, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Défaut RestaurantGuru — écrasé par doc["business_score"] quand explicite (sources externes)
BUSINESS_SCORE_DEFAULT = 0.6

# "€" → 1, "€€" → 2, "€€€" → 3, "€€€€" → 4
BUDGET_TO_PRICE_LEVEL: Dict[str, Tuple[int, int]] = {
    "low":     (0, 1),
    "medium":  (1, 2),
    "luxury":  (3, 4),
    "premium": (3, 4),
}


class MongoRestaurantService:

    # ── Helpers ──────────────────────────────────────────────────────────

    @staticmethod
    def _parse_price_level(price_str: Optional[str]) -> Optional[int]:
        """Convertit "€€" → 2. Retourne None si absent ou non reconnu."""
        if not price_str:
            return None
        count = price_str.count("€")
        return count if 1 <= count <= 4 else None

    @staticmethod
    def _haversine(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
        R = 6371.0
        p1, p2 = math.radians(lat1), math.radians(lat2)
        dp = math.radians(lat2 - lat1)
        dl = math.radians(lng2 - lng1)
        a  = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
        return round(R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a)), 2)

    @staticmethod
    def _to_candidate(
        doc: Dict,
        ref_lat: Optional[float] = None,
        ref_lng: Optional[float] = None,
    ) -> Dict:
        """
        Mappe un document MongoDB vers le format RestaurantCandidate.
        Gère les deux schémas coexistants :
          - RestaurantGuru : categories, geo, zone, restaurantguru_url
          - TripAdvisor    : cuisines, city_slug, tripadvisor_url (pas de geo ni zone)
        """
        # GPS — uniquement RestaurantGuru
        geo = doc.get("geo") or {}
        lat = geo.get("lat")
        lng = geo.get("lng")

        distance_km = None
        if lat and lng and ref_lat is not None and ref_lng is not None:
            distance_km = MongoRestaurantService._haversine(ref_lat, ref_lng, lat, lng)

        # Cuisine types — "categories" (RestaurantGuru) OU "cuisines" (TripAdvisor)
        cuisine_types = doc.get("categories") or doc.get("cuisines") or []

        # Description — RestaurantGuru natif, sinon construction depuis tags + features
        description = doc.get("description")
        if not description:
            parts = []
            tags     = doc.get("tags") or []
            features = doc.get("features") or []
            if tags:     parts.append(", ".join(tags[:5]))
            if features: parts.append(", ".join(features[:3]))
            description = " | ".join(parts) or None

        # Source URL et source label
        source_url = doc.get("restaurantguru_url") or doc.get("tripadvisor_url")
        source_label = doc.get("source", "unknown")

        return {
            "id":                 str(doc["_id"]),
            "name":               doc.get("name", ""),
            "description":        description,
            "address":            doc.get("address"),
            "lat":                lat,
            "lng":                lng,
            "rating":             doc.get("rating"),
            "user_ratings_total": doc.get("reviews"),
            "price_level":        MongoRestaurantService._parse_price_level(doc.get("price_level")),
            "cuisine_types":      cuisine_types,
            "is_open_now":        None,
            "distance_km":        distance_km,
            "photo_reference":    doc.get("photo_url"),
            "match_score":        0.0,
            "matched_criteria":   [],
            "establishment_types": doc.get("establishment_types") or [],
            "tier":               "mongodb",
            "source":             source_label,
            "_city":              doc.get("city"),
            "_zone":              doc.get("zone"),
            "_source_url":        source_url,
        }

    # ── Filtres MongoDB ───────────────────────────────────────────────────

    @staticmethod
    def _city_zone_filter(destination: str) -> Dict:
        """
        Construit un filtre MongoDB OR :
          city  == destination (exact, insensible à la casse)
          zone  contient destination (ex: "Sousse" dans "Gouvernorat de Sousse")
        """
        escaped = re.escape(destination.strip())
        return {
            "$or": [
                {"city": {"$regex": f"^{escaped}$",  "$options": "i"}},
                {"zone": {"$regex": escaped,          "$options": "i"}},
            ]
        }

    @staticmethod
    def _keyword_filter(keywords: List[str]) -> Optional[Dict]:
        """
        Filtre souple sur categories + tags + description.
        Même logique de stemming que RestaurantServiceA.score().
        """
        stems = []
        for kw in keywords:
            stem = kw.lower()
            for suffix in ("restaurant", "dining", "food", "cuisine", "cafe", "eating"):
                stem = stem.replace(suffix, "")
            stem = stem.strip()
            if len(stem) >= 3:
                stems.append(stem)

        if not stems:
            return None

        or_clauses = []
        for stem in stems:
            escaped = re.escape(stem)
            or_clauses.extend([
                {"categories":  {"$regex": escaped, "$options": "i"}},  # RestaurantGuru
                {"cuisines":    {"$regex": escaped, "$options": "i"}},  # TripAdvisor
                {"tags":        {"$regex": escaped, "$options": "i"}},
                {"description": {"$regex": escaped, "$options": "i"}},
                {"features":    {"$regex": escaped, "$options": "i"}},
            ])
        return {"$or": or_clauses}

    # ── Scoring ───────────────────────────────────────────────────────────

    @staticmethod
    def score(
        candidate: Dict,
        keywords:     List[str],
        budget_level: Optional[str],
        is_family:    bool,
    ) -> Tuple[float, List[str]]:
        """Score 0 → 1 : rating (35%) + budget (20%) + keyword (30%) + famille (15%)."""
        s        = 0.0
        criteria = []

        # Rating (max 0.35)
        rating = candidate.get("rating") or 0.0
        if rating >= 4.5:
            s += 0.35; criteria.append("rating_excellent")
        elif rating >= 4.0:
            s += 0.25; criteria.append("rating_good")
        elif rating >= 3.5:
            s += 0.15; criteria.append("rating_ok")

        # Budget → price_level (0.20)
        price_level = candidate.get("price_level")
        if price_level is not None and budget_level:
            lo, hi = BUDGET_TO_PRICE_LEVEL.get(budget_level, (0, 4))
            if lo <= price_level <= hi:
                s += 0.20; criteria.append("budget_match")

        # Keyword match (max 0.30)
        if keywords:
            searchable = " ".join(filter(None, [
                (candidate.get("name")        or "").lower(),
                (candidate.get("description") or "").lower(),
                " ".join(candidate.get("cuisine_types") or []).lower(),
            ]))
            matched = []
            for kw in keywords:
                stem = kw.lower()
                for suffix in ("restaurant", "dining", "food", "cuisine", "cafe", "eating"):
                    stem = stem.replace(suffix, "")
                stem = stem.strip()
                if len(stem) >= 3 and stem in searchable:
                    matched.append(kw)
            if matched:
                ratio = len(matched) / len(keywords)
                s += round(min(0.30, ratio * 0.30), 4)
                criteria.append("keyword_match")

        # Famille (0.15)
        if is_family:
            tags_str = " ".join(
                (candidate.get("cuisine_types") or [])
            ).lower()
            if any(w in tags_str for w in ("famille", "family", "enfant", "child")):
                s += 0.15; criteria.append("family_match")

        return round(min(s, 1.0), 4), criteria

    # ── Point d'entrée principal ──────────────────────────────────────────

    @staticmethod
    def search(
        destination:  Optional[str],
        keywords:     List[str],
        budget_level: Optional[str],
        is_family:    bool,
        ref_lat:      Optional[float] = None,
        ref_lng:      Optional[float] = None,
        max_results:  int = 15,
    ) -> List[Dict]:
        """
        Recherche restaurants dans MongoDB par city + zone + destination.

        Stratégie :
          1. Filtre strict  : city/zone + keywords → si >= 3 résultats → retourne
          2. Filtre relâché : city/zone uniquement (ignore keywords)
          3. Tri par match_score DESC

        Retourne une liste de dicts compatibles RestaurantCandidate.
        """
        if not destination:
            return []

        try:
            from app.config.mongodb import restaurant_collection
            col = restaurant_collection()

            location_filter = MongoRestaurantService._city_zone_filter(destination)
            kw_filter       = MongoRestaurantService._keyword_filter(keywords)

            # ── Passe 1 : location + keywords ──────────────────────────────
            if kw_filter:
                query  = {"$and": [location_filter, kw_filter]}
                docs   = list(col.find(query).sort("rating", -1).limit(max_results * 3))
                source = "strict"
            else:
                docs   = []
                source = "relaxed"

            # ── Passe 2 : location uniquement (relax) ──────────────────────
            if len(docs) < 3:
                docs   = list(col.find(location_filter).sort("rating", -1).limit(max_results * 3))
                source = "relaxed"

            logger.info(
                f"MongoRestaurantService: destination='{destination}' "
                f"source={source} docs={len(docs)}"
            )

            if not docs:
                return []

            # ── Conversion + scoring ────────────────────────────────────────
            candidates = [
                MongoRestaurantService._to_candidate(doc, ref_lat, ref_lng)
                for doc in docs
            ]

            for c, doc in zip(candidates, docs):
                sc, crit = MongoRestaurantService.score(c, keywords, budget_level, is_family)
                c["match_score"]    = sc
                c["matched_criteria"] = crit
                # Priorite au business_score explicite du doc (ex. 0.20 pour les
                # etablissements enrichis via SerpApi/Google) — sinon defaut RestaurantGuru.
                c["business_score"] = doc.get("business_score", BUSINESS_SCORE_DEFAULT)

            candidates.sort(key=lambda x: x["match_score"], reverse=True)
            return candidates[:max_results]

        except Exception as e:
            logger.error(f"MongoRestaurantService.search error: {e}")
            return []
