"""
MongoRestaurantService — Tier 1 source pour les candidats restaurants.

Recherche dans restaurant_collection via MongoDB Atlas Search (index
"restaurant_search" — cf. create_restaurant_search_index.py) :
  - filtre dur   : city/zone (destination) + establishment_types (créneau, optionnel)
  - pertinence   : categories (boost x3) + tags (boost x2) + description,
                   sur les mots-clés sémantiques normalisés (stem_keyword)

Remplace le filtrage par expressions régulières (migration 2026-07-23) —
une seule requête au lieu de 2 passes stricte/relâchée, scoring de
pertinence natif au lieu d'un match binaire.

business_score = 0.6 par défaut (données propres, zéro coût API, source vérifiée) ;
priorité à la valeur explicite du document si présente (ex. 0.20 pour les
établissements enrichis via SerpApi/Google).
Fallback Google Places/SerpApi (restaurant_service.py) si résultats < seuil.
"""

import logging
import math
import re
from typing import Dict, Any, List, Optional, Tuple

from app.config.settings import RESTAURANT_PROXIMITY_MAX_KM

logger = logging.getLogger(__name__)

SEARCH_INDEX_NAME = "restaurant_search"

# Défaut RestaurantGuru — écrasé par doc["business_score"] quand explicite (sources externes)
BUSINESS_SCORE_DEFAULT = 0.6

# "€" → 1, "€€" → 2, "€€€" → 3, "€€€€" → 4
BUDGET_TO_PRICE_LEVEL: Dict[str, Tuple[int, int]] = {
    "low":     (0, 1),
    "medium":  (1, 2),
    "luxury":  (3, 4),
    "premium": (3, 4),
}

# Suffixes composites du vocabulaire semantic_node (ex. "seafoodRestaurant" -> "seafood")
# — un seul suffixe retire en fin de mot, jamais en cascade.
_KEYWORD_SUFFIXES = ("restaurant", "dining", "food", "cuisine", "cafe", "eating")

# Regex horaires — formats tunisiens : "12:00-23:00", "11h30-14h30", "19h-22h30"
# Capture uniquement les heures (minutes ignorées — précision heure suffisante).
_TIME_RE = re.compile(
    r'(\d{1,2})\s*[h:]\s*\d{0,2}\s*[-–]\s*(\d{1,2})\s*[h:]\s*\d{0,2}',
    re.IGNORECASE,
)

# Poids scoring restaurant V2 — 6 dimensions, somme = 1.00.
# proximity et hours retournent 0.5 (neutre) quand le signal est absent.
_SCORE_WEIGHTS = {
    "rel":       0.35,
    "rating":    0.25,
    "zone":      0.10,
    "budget":    0.10,
    "proximity": 0.10,
    "hours":     0.10,
}
_SCORE_TOTAL = sum(_SCORE_WEIGHTS.values())  # 1.00


def stem_keyword(kw: str) -> str:
    stem = str(kw).lower().strip()
    for suffix in _KEYWORD_SUFFIXES:
        if stem.endswith(suffix) and len(stem) > len(suffix):
            return stem[: -len(suffix)].strip()
    return stem


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
    def _proximity_score(distance_km: Optional[float]) -> float:
        """1.0 à 0 km, décroissance linéaire, plancher 0.1 à RESTAURANT_PROXIMITY_MAX_KM.
        Retourne 0.5 (neutre) quand distance_km est None (signal absent)."""
        if distance_km is None:
            return 0.5
        return round(max(0.1, 1.0 - float(distance_km) / RESTAURANT_PROXIMITY_MAX_KM), 4)

    @staticmethod
    def _hours_score(opening_hours_text: Optional[str], request_hour: Optional[int]) -> float:
        """1.0 si probablement ouvert, 0.3 si probablement fermé, 0.5 si inconnu.
        Neutre (0.5) quand request_hour est None ou format non parseable."""
        if not opening_hours_text or request_hour is None:
            return 0.5
        t = opening_hours_text.lower()
        if "24h" in t or "24/7" in t:
            return 1.0
        matches = _TIME_RE.findall(t)
        if not matches:
            return 0.5
        for h_open_s, h_close_s in matches:
            open_h  = int(h_open_s)
            close_h = int(h_close_s)
            if close_h == 0:
                close_h = 24  # "00:00" en fermeture = minuit
            if open_h <= request_hour < close_h:
                return 1.0
            # Chevauchement minuit (ex. 20h-02h)
            if close_h < open_h and (request_hour >= open_h or request_hour < close_h):
                return 1.0
        return 0.3

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
            "user_score":         0.0,
            "matched_criteria":   [],
            "establishment_types": doc.get("establishment_types") or [],
            "tier":               "mongodb",
            "source":             source_label,
            "_city":              doc.get("city"),
            "_zone":              doc.get("zone"),
            "_source_url":        source_url,
            "opening_hours_text": doc.get("opening_hours_text"),
        }

    # ── Pipeline Atlas Search ───────────────────────────────────────────────

    @staticmethod
    def _build_search_pipeline(
        destination: str,
        stems: List[str],
        establishment_types: Optional[List[str]],
        max_results: int,
    ) -> List[Dict]:
        """
        Couche 1 (filtre dur) : destination (city/zone) + establishment_types
        si fourni (créneau horaire ou préférence mappée, cf. restaurant_node).
        Couche 2 (pertinence) : categories (boost x3) + tags (boost x2) +
        features (boost x1.5, ex. "livraison"/"terrasse") + description,
        sur les mots-clés déjà stemmés. searchScore exposé via $meta pour
        normalisation en Python.
        """
        compound: Dict[str, Any] = {
            "filter": [{"text": {"query": destination, "path": ["city", "zone"]}}],
            "should": [],
        }
        if establishment_types:
            compound["filter"].append(
                {"text": {"query": establishment_types, "path": "establishment_types"}}
            )
        if stems:
            compound["should"] = [
                {"text": {"query": stems, "path": "categories",
                          "score": {"boost": {"value": 3}}}},
                {"text": {"query": stems, "path": "tags",
                          "score": {"boost": {"value": 2}}}},
                {"text": {"query": stems, "path": "features",
                          "score": {"boost": {"value": 1.5}}}},
                {"text": {"query": stems, "path": "description"}},
            ]

        return [
            {"$search": {"index": SEARCH_INDEX_NAME, "compound": compound}},
            {"$limit": max_results * 3},
            {"$addFields": {"search_relevance": {"$meta": "searchScore"}}},
        ]

    # ── Scoring — formule V2 (2026-08-06) ───────────────────────────────────
    #   user_score = rel(35%) + rating(25%) + zone(10%) + budget(10%)
    #              + proximity(10%) + hours(10%)   → divisé par _SCORE_TOTAL (1.00)
    #   proximity : 1.0 à 0 km, décroissance linéaire, 0.1 à RESTAURANT_PROXIMITY_MAX_KM
    #               0.5 (neutre) si distance_km=None (pas de GPS de référence)
    #   hours     : 1.0 si ouvert maintenant, 0.3 si fermé, 0.5 si inconnu/no request_hour
    #   business_score extrait séparément → business_boost appliqué par ranking_node
    # is_family conservé dans la signature pour compatibilité d'appel
    # (restaurant_service.py) mais n'entre pas dans cette formule.

    @staticmethod
    def _rating_confiance(rating: Optional[float], reviews: Optional[int]) -> float:
        """Note pondérée par le volume d'avis. Absence de rating -> neutre (0.5), jamais 0."""
        if rating is None:
            return 0.5
        normalized = max(0.0, min(1.0, (float(rating) - 1) / 4))
        confidence = max(0.5, min(1.0, math.log((reviews or 0) + 1) / math.log(50))) if reviews else 0.5
        return round(normalized * (0.5 + 0.5 * confidence), 4)

    @staticmethod
    def _zone_priority(doc_city: Optional[str], destination: str) -> float:
        """1.0 si match exact sur city, 0.6 si remonté via zone (gouvernorat) seulement."""
        return 1.0 if (doc_city or "").strip().lower() == destination.strip().lower() else 0.6

    @staticmethod
    def _budget_soft_match(price_level: Optional[int], budget_level: Optional[str]) -> float:
        """Score budget continu sur l'échelle 0-4 (price_level Google).
        Dans la fourchette → 1.0 ; hors fourchette → décroissance linéaire,
        plancher 0.1 (jamais exclu complètement — pas de double-comptage)."""
        if price_level is None or not budget_level:
            return 0.5
        lo, hi = BUDGET_TO_PRICE_LEVEL.get(budget_level, (0, 4))
        pl = float(price_level)
        if lo <= pl <= hi:
            return 1.0
        dist = (pl - hi) if pl > hi else (lo - pl)
        return round(max(0.1, 1.0 - dist / 4.0), 4)

    @staticmethod
    def score(
        candidate:             Dict,
        keywords:              List[str],
        budget_level:          Optional[str],
        is_family:             bool,
        search_relevance_norm: float = 0.0,
        destination:           str = "",
        request_hour:          Optional[int] = None,
    ) -> Tuple[float, List[str]]:
        criteria = []

        rel = search_relevance_norm
        if rel > 0.5:
            criteria.append("high_relevance")

        rating_c = MongoRestaurantService._rating_confiance(
            candidate.get("rating"), candidate.get("user_ratings_total")
        )
        if rating_c > 0.7:
            criteria.append("rating_good")

        zone_p = MongoRestaurantService._zone_priority(candidate.get("_city"), destination)
        if zone_p == 1.0:
            criteria.append("exact_city")

        budget_s = MongoRestaurantService._budget_soft_match(
            candidate.get("price_level"), budget_level
        )
        if budget_s == 1.0:
            criteria.append("budget_match")

        proximity_s = MongoRestaurantService._proximity_score(candidate.get("distance_km"))
        if proximity_s < 0.5:
            criteria.append("proximity_far")

        hours_s = MongoRestaurantService._hours_score(
            candidate.get("opening_hours_text"), request_hour
        )
        if hours_s == 0.3:
            criteria.append("possibly_closed")

        user_s = (
            rel         * _SCORE_WEIGHTS["rel"]       +
            rating_c    * _SCORE_WEIGHTS["rating"]    +
            zone_p      * _SCORE_WEIGHTS["zone"]      +
            budget_s    * _SCORE_WEIGHTS["budget"]    +
            proximity_s * _SCORE_WEIGHTS["proximity"] +
            hours_s     * _SCORE_WEIGHTS["hours"]
        ) / _SCORE_TOTAL

        return round(min(user_s, 1.0), 4), criteria

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
        establishment_types: Optional[List[str]] = None,
        halal_required: bool = False,
        request_hour: Optional[int] = None,
    ) -> List[Dict]:
        """
        Recherche restaurants via Atlas Search (index "restaurant_search") :
        filtre dur destination (+ establishment_types si fourni), pertinence
        native sur categories/tags/description. Une seule requête — plus de
        passe stricte/relâchée séparée : un doc sans match de mot-clé remonte
        quand même via le filtre destination, juste moins bien classé.
        """
        if not destination:
            return []

        try:
            from app.config.mongodb import restaurant_collection
            col = restaurant_collection()

            stems = [s for s in (stem_keyword(k) for k in keywords) if len(s) >= 3]
            pipeline = MongoRestaurantService._build_search_pipeline(
                destination, stems, establishment_types, max_results
            )
            docs = list(col.aggregate(pipeline))

            # Halal : exclure les bars purs (establishment_types ne contient que "bar",
            # sans "restaurant" ni "cafe"). Les bars avec un type restaurant/cafe (ex.
            # "Aoussou Café Bar") sont conservés. Docs explicitement halal aussi.
            if halal_required:
                docs = [
                    d for d in docs
                    if (
                        "bar" not in (d.get("establishment_types") or [])
                        or "restaurant" in (d.get("establishment_types") or [])
                        or "cafe" in (d.get("establishment_types") or [])
                        or any("halal" in (c or "").lower() for c in (d.get("categories") or []))
                        or any("halal" in (t or "").lower() for t in (d.get("tags") or []))
                    )
                ]

            logger.info(
                f"MongoRestaurantService: destination='{destination}' "
                f"establishment_types={establishment_types} halal={halal_required} docs={len(docs)}"
            )

            if not docs:
                return []

            # ── Normalisation min-max de search_relevance (searchScore Lucene
            # non borné 0-1) sur le lot retourné ──────────────────────────
            raw_scores = [d.get("search_relevance", 0.0) for d in docs]
            lo_s, hi_s = min(raw_scores), max(raw_scores)
            spread = hi_s - lo_s

            # ── Conversion + scoring ────────────────────────────────────────
            candidates = [
                MongoRestaurantService._to_candidate(doc, ref_lat, ref_lng)
                for doc in docs
            ]

            for c, doc in zip(candidates, docs):
                raw_rel = doc.get("search_relevance", 0.0)
                rel_norm = (raw_rel - lo_s) / spread if spread > 0 else 1.0

                # Priorite au business_score explicite du doc (ex. 0.20 pour les
                # etablissements enrichis via SerpApi/Google) — sinon defaut RestaurantGuru.
                c["business_score"] = doc.get("business_score", BUSINESS_SCORE_DEFAULT)

                sc, crit = MongoRestaurantService.score(
                    c, keywords, budget_level, is_family,
                    search_relevance_norm=rel_norm, destination=destination,
                    request_hour=request_hour,
                )
                c["user_score"]     = sc
                c["matched_criteria"] = crit

            candidates.sort(key=lambda x: x["user_score"], reverse=True)
            return candidates[:max_results]

        except Exception as e:
            logger.error(f"MongoRestaurantService.search error: {e}")
            return []
