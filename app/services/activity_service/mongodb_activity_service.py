"""
SOURCE 2 — Activités externes (MongoDB Atlas)
Base remplie par le scraper TripAdvisor/SerpAPI par ville tunisienne.
business_score = 0.2 (enrichissement expérience, pas de commission directe)
"""
import logging
from typing import Any, Dict, List, Optional, Tuple

from app.services.activity_service.scoring import budget_proximity_score

logger = logging.getLogger(__name__)

BUSINESS_SCORE = 0.2

BUDGET_TO_PRICE_EUR: Dict[str, Tuple[float, float]] = {
    "low":     (0,   20),
    "medium":  (20,  60),
    "luxury":  (60, 999),
    "premium": (60, 999),
}

# Macro-catégories depuis tags MongoDB
ACTIVITY_TYPE_MAP: Dict[str, List[str]] = {
    "culture":         ["historique", "culture", "patrimoine", "ruines", "monument",
                        "musée", "mosquée", "synagogue", "archéologique", "histoire"],
    "nature":          ["plage", "mer", "nature", "oasis", "forêt", "montagne",
                        "sahara", "désert", "dune", "parc"],
    "adventure":       ["aventure", "safari", "quad", "plongée", "surf",
                        "randonnée", "kite", "4x4", "jet ski"],
    "relax":           ["spa", "hammam", "détente", "repos", "golf",
                        "bien-être", "massage", "thalasso"],
    "city_experience": ["souk", "marché", "shopping", "balade", "marina",
                        "port", "promenade", "médina", "ville"],
}

# Mapping traveler_type MongoDB → profil voyageur
TRAVELER_TYPE_MAP: Dict[str, str] = {
    "culture":  "solo",
    "histoire": "solo",
    "famille":  "family",
    "couple":   "couple",
    "aventure": "solo",
    "nature":   "solo",
}


def _infer_activity_type(tags: List[str], category: str) -> str:
    """Macro-catégorie depuis les tags + catégorie TripAdvisor."""
    combined = " ".join(tags).lower() + " " + (category or "").lower()
    for activity_type, keywords in ACTIVITY_TYPE_MAP.items():
        if any(kw in combined for kw in keywords):
            return activity_type
    return "unknown"


def _compute_user_score(
    doc: Dict[str, Any],
    global_keywords: List[str],
    budget_level: Optional[str],
    traveler_type: Optional[str],
) -> Tuple[float, List[str]]:
    """
    user_score 0.0→1.0 pour un document MongoDB
      keyword match (tags + name)  0.35
      rating                       0.25
      budget (price_from_eur)      0.20
      traveler_type match          0.20
    """
    s: float = 0.0
    criteria: List[str] = []

    tags     = [t.lower() for t in (doc.get("tags") or [])]
    name     = (doc.get("name") or "").lower()
    desc     = (doc.get("description") or "").lower()
    searchable = name + " " + desc + " " + " ".join(tags)

    # Keyword match (0.35)
    if global_keywords:
        matched = [kw for kw in global_keywords if kw.lower() in searchable]
        if matched:
            s += round(min(0.35, len(matched) / len(global_keywords) * 0.35), 4)
            criteria.append("keyword_match")

    # Rating (0.25) — TripAdvisor scale 1→5
    rating = float(doc.get("rating") or 0)
    if rating >= 4.5:
        s += 0.25; criteria.append("rating_excellent")
    elif rating >= 4.0:
        s += 0.18; criteria.append("rating_good")
    elif rating >= 3.5:
        s += 0.10; criteria.append("rating_ok")

    # Budget vs price_from_eur (0.20) — score continu partagé
    price = doc.get("price_from_eur")
    if budget_level and price is not None:
        b = budget_proximity_score(float(price), budget_level, BUDGET_TO_PRICE_EUR)
        s += b
        if b >= 0.15:
            criteria.append("budget_match")
        elif b > 0:
            criteria.append("budget_partial")
    elif price is None:
        # activité gratuite → compatible tous budgets
        s += 0.10; criteria.append("free_activity")

    # Traveler type (0.20)
    if traveler_type:
        traveler_types_doc = [t.lower() for t in (doc.get("traveler_types") or [])]
        if traveler_type in traveler_types_doc:
            s += 0.20; criteria.append("traveler_type_match")
        elif any(
            TRAVELER_TYPE_MAP.get(t) == traveler_type
            for t in traveler_types_doc
        ):
            s += 0.10; criteria.append("traveler_type_partial")

    return round(min(s, 1.0), 4), criteria


def _build_recommendation_context(doc: Dict[str, Any]) -> str:
    """Contexte lisible pour le ranking_node LLM."""
    activity_type = _infer_activity_type(
        doc.get("tags") or [], doc.get("category") or ""
    )
    type_labels = {
        "culture":         "Site culturel",
        "nature":          "Activité nature",
        "adventure":       "Activité aventure",
        "relax":           "Détente & bien-être",
        "city_experience": "Expérience ville",
        "unknown":         "Activité locale",
    }
    label = type_labels.get(activity_type, "Activité locale")
    dest  = doc.get("destination") or ""
    return f"{label} à {dest}" if dest else label


def get_candidates(
    destination: Optional[str],
    global_keywords: List[str],
    budget_level: Optional[str],
    traveler_type: Optional[str],
    max_candidates: int = 10,
) -> List[Dict[str, Any]]:
    """
    Retourne les candidats SOURCE 2 depuis MongoDB Atlas.
    Filtre par destination_id, score par keywords + rating + budget + traveler_type.
    score = 0.7 * user_score + 0.3 * 0.2
    """
    if not destination:
        logger.info("[MongoActivityService] pas de destination — retour []")
        return []

    try:
        from app.config.mongodb import activities_collection
        col = activities_collection()
    except Exception as e:
        logger.error(f"[MongoActivityService] connexion MongoDB échouée: {e}")
        return []

    dest_id = destination.lower().strip()

    # Filtre MongoDB : destination + type attraction/tour (pas restaurant)
    mongo_filter: Dict[str, Any] = {
        "destination_id": dest_id,
        "type":           {"$in": ["attraction", "tour"]},
    }

    # Filtre optionnel par tags si keywords fournis
    if global_keywords:
        kw_lower = [kw.lower() for kw in global_keywords]
        mongo_filter["$or"] = [
            {"tags":        {"$in": kw_lower}},
            {"traveler_types": {"$in": kw_lower}},
        ]

    try:
        cursor = col.find(mongo_filter).sort("rating", -1).limit(max_candidates * 3)
        raw_docs = list(cursor)
    except Exception as e:
        logger.error(f"[MongoActivityService] query MongoDB: {e}")
        return []

    if not raw_docs:
        # Fallback sans filtre keywords — toutes les activités de la destination
        try:
            cursor = (
                col.find({"destination_id": dest_id, "type": {"$in": ["attraction", "tour"]}})
                .sort("rating", -1)
                .limit(max_candidates)
            )
            raw_docs = list(cursor)
        except Exception as e:
            logger.error(f"[MongoActivityService] fallback query: {e}")
            return []

    candidates: List[Dict[str, Any]] = []

    for doc in raw_docs:
        tags          = doc.get("tags") or []
        category      = doc.get("category") or ""
        activity_type = _infer_activity_type(tags, category)
        price_eur     = doc.get("price_from_eur")

        user_score, matched_criteria = _compute_user_score(
            doc, global_keywords or [], budget_level, traveler_type
        )
        score = round(0.7 * user_score + 0.3 * BUSINESS_SCORE, 4)

        doc_id = str(doc.get("_id", "")) or doc.get("name", "")

        candidates.append({
            "id":                     doc_id,
            "name":                   doc.get("name") or "",
            "description":            doc.get("description"),
            "activity_type":          activity_type,
            "source":                 "mongodb",
            "tier":                   "external",
            "activity_id":            doc_id,
            "booking_reference":      "",
            "hotel_name":             None,
            "destination":            doc.get("destination") or destination,
            "zone":                   doc.get("region"),
            "date":                   None,
            "recurrence_start":       None,
            "recurrence_end":         None,
            "recurrence_days":        [],
            "adult_price":            float(price_eur) if price_eur is not None else 0.0,
            "child_price":            0.0,
            "baby_price":             0.0,
            "currency":               "EUR" if price_eur is not None else "TND",
            "duration_hours":         None,
            "max_participants":       0,
            "registered_participants": 0,
            "available_spots":        None,
            "is_available":           None,   # inconnu — MongoDB ne vérifie pas la dispo réelle
            "already_booked":         False,
            "has_geospatial_info":    False,
            "distance_km":            None,
            "travel_time_min":        None,
            "rating":                 float(doc.get("rating") or 0),
            "reviews_count":          int(doc.get("reviews_count") or 0),
            "score":                  score,
            "business_score":         round(BUSINESS_SCORE, 4),
            "user_score":             round(user_score, 4),
            "matched_criteria":       matched_criteria,
            "semantic_tags":          tags,
            "recommendation_context": _build_recommendation_context(doc),
            "recommendation_reason":  None,
        })

    candidates.sort(key=lambda x: x["score"], reverse=True)

    logger.info(
        f"[MongoActivityService] {len(candidates[:max_candidates])} candidats | "
        f"destination={destination} | raw_docs={len(raw_docs)}"
    )
    return candidates[:max_candidates]


class MongoActivityService:
    """Wrapper classe pour usage cohérent avec InternalActivityService."""

    @staticmethod
    def get_candidates(
        destination: Optional[str],
        global_keywords: List[str],
        budget_level: Optional[str],
        traveler_type: Optional[str],
        max_candidates: int = 10,
    ) -> List[Dict[str, Any]]:
        return get_candidates(
            destination=destination,
            global_keywords=global_keywords,
            budget_level=budget_level,
            traveler_type=traveler_type,
            max_candidates=max_candidates,
        )
