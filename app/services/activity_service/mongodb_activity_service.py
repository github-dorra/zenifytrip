"""
SOURCE 2 — Activités externes (MongoDB Atlas)
Base remplie par le scraper TripAdvisor/SerpAPI par ville tunisienne.
business_score = 0.2 (enrichissement expérience, pas de commission directe)
"""
import logging
import re
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

from app.services.activity_service.scoring import budget_proximity_score
from app.config.settings import USER_SCORE_WEIGHT, BUSINESS_SCORE_WEIGHT

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

# Mapping profil inféré → valeur champ "audience" MongoDB (enrichi en Phase 5)
_TRAVELER_TO_AUDIENCE: Dict[str, str] = {
    "family": "famille",
    "couple": "couple",
    "solo":   "solo",
}

# Mapping mois → saison (hémisphère nord, Tunisie)
_MONTH_TO_SEASON: Dict[int, str] = {
    1: "hiver",    2: "hiver",    3: "printemps",
    4: "printemps", 5: "printemps", 6: "été",
    7: "été",      8: "été",      9: "automne",
    10: "automne", 11: "automne", 12: "hiver",
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
    beach_score: float = 0.0,
    search_score: Optional[float] = None,
) -> Tuple[float, List[str]]:
    """
    user_score 0.0→1.0 pour un document MongoDB
      keyword match (tags + name + description)  0.35
      rating                                     0.25
      budget (price_from_eur)                    0.20
      traveler_type match                        0.20
      [bonus] best_season match                 +0.05
      [bonus] beach boost (si beach_score≥0.7)  +0.05
    Clamped à 1.0 — les bonus poussent les bons candidats sans créer de faux positifs.
    search_score: Atlas Search score (si disponible) — remplace le calcul keyword manuel
    """
    s: float = 0.0
    criteria: List[str] = []

    tags     = [t.lower() for t in (doc.get("tags") or [])]
    name     = (doc.get("name") or "").lower()
    desc     = (doc.get("description") or "").lower()
    searchable = name + " " + desc + " " + " ".join(tags)

    # Keyword match (0.35)
    # Si Atlas Search score disponible : on l'utilise directement (cross-langue)
    # Sinon : fallback sur substring match basique
    if search_score is not None:
        # Normalise : Atlas Search retourne 0→∞, on plafonne à ~5 pour avoir 0→1
        normalized = min(search_score / 5.0, 1.0)
        s += round(normalized * 0.35, 4)
        if normalized > 0.1:
            criteria.append("atlas_search_match")
    elif global_keywords:
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

    # Bonus saisonnier (+0.05) — champ best_season enrichi en Phase 5
    current_season = _MONTH_TO_SEASON[date.today().month]
    seasons = doc.get("best_season") or []
    if isinstance(seasons, str):
        seasons = [seasons]
    if current_season in seasons or "toute_année" in seasons:
        s += 0.05; criteria.append("season_match")

    # Bonus plage (+0.05) — boost si météo indique forte probabilité de plage
    if beach_score >= 0.7 and (doc.get("activity_type") or "") == "nature":
        s += 0.05; criteria.append("beach_boost")

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


def _normalize_keywords(keywords: List[str]) -> str:
    """
    Prépare la query string pour Atlas Search.
    Split camelCase + underscores : 'culturalActivity' → 'cultural activity'
    Permet au dual-analyzer (lucene.french + lucene.english) de matcher les tags FR.
    Ex: 'cultural' (EN) → stem 'cultur' ↔ 'culture' (FR tag) → stem 'cultur' → MATCH.
    """
    tokens: List[str] = []
    for kw in keywords:
        # 1. underscores → espaces : outdoor_activity → outdoor activity
        kw = kw.replace("_", " ")
        # 2. camelCase → espaces : culturalActivity → cultural Activity
        kw = re.sub(r"([a-z])([A-Z])", r"\1 \2", kw)
        tokens.extend(kw.lower().split())
    return " ".join(dict.fromkeys(tokens))  # dédupliquer en préservant l'ordre


def _build_atlas_search_pipeline(
    dest_id: str,
    keywords: List[str],
    indoor_preference: Optional[bool],
    traveler_type: Optional[str],
    max_candidates: int,
) -> List[Dict[str, Any]]:
    """
    Construit la pipeline $search Atlas Search avec dual-analyzer.
    Index 'activities_search' a deux paths par champ :
      tags (lucene.french)  : 'culture' → stem 'cultur'
      tags.en (lucene.english): 'cultural' → stem 'cultur'  ← cross-langue !
    Les deux clauses should permettent de matcher les keywords EN contre les tags FR.
    $match (post-search) : destination_id + filtres durs (B-tree index, plus fiable
    que text operator pour les champs keyword).
    """
    # Split camelCase/underscores pour que le dual-analyzer puisse travailler
    kw_query = _normalize_keywords(keywords) if keywords else "activité"

    compound: Dict[str, Any] = {
        "should": [
            # Clause FR : analyse avec lucene.french → matche les tags français
            {
                "text": {
                    "query": kw_query,
                    "path":  ["tags", "category", "name"],
                    "fuzzy": {"maxEdits": 1},
                }
            },
            # Clause EN : analyse avec lucene.english → 'cultural'→cultur ↔ 'culture'→cultur
            {
                "text": {
                    "query": kw_query,
                    "path":  ["tags.en", "category.en", "name.en", "activity_type"],
                }
            },
        ],
        "minimumShouldMatch": 1,
    }

    # Filtres durs dans $match APRÈS $search (destination + type + météo + audience)
    post_match: Dict[str, Any] = {
        "destination_id": dest_id,
        "type": {"$in": ["attraction", "tour", "activity"]},
    }
    if indoor_preference is not None:
        post_match["indoor"] = indoor_preference
    if traveler_type in ("family", "couple"):
        audience_val = _TRAVELER_TO_AUDIENCE.get(traveler_type)
        if audience_val:
            post_match["audience"] = audience_val

    pipeline = [
        {"$search": {"index": "activities_search", "compound": compound}},
        {"$addFields": {"search_score": {"$meta": "searchScore"}}},
        {"$match": post_match},
        {"$limit": max_candidates * 4},
    ]
    return pipeline


def get_candidates(
    destination: Optional[str],
    global_keywords: List[str],
    budget_level: Optional[str],
    traveler_type: Optional[str],
    max_candidates: int = 10,
    indoor_preference: Optional[bool] = None,
    beach_score: float = 0.0,
) -> List[Dict[str, Any]]:
    """
    Retourne les candidats SOURCE 2 depuis MongoDB Atlas.
    Couche 1 — $search Atlas Search (french+english, fuzzy) sur destination + keywords.
    Fallback — filtre classique si Atlas Search indisponible.
    Couche 2 — scoring : search_score + rating + budget + traveler_type + saison + plage.
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

    # ── COUCHE 1 : Atlas Search ───────────────────────────────────────
    raw_docs: List[Dict[str, Any]] = []
    atlas_available = False

    try:
        pipeline = _build_atlas_search_pipeline(
            dest_id, global_keywords or [], indoor_preference, traveler_type, max_candidates
        )
        raw_docs = list(col.aggregate(pipeline))
        atlas_available = True
        logger.info(
            f"[MongoActivityService] Atlas Search OK | {len(raw_docs)} docs | "
            f"dest={dest_id} | kw={global_keywords[:4]}"
        )
    except Exception as e:
        logger.warning(f"[MongoActivityService] Atlas Search indisponible ({e}) — fallback filtre classique")

    # ── FALLBACK : filtre classique si Atlas Search indisponible ─────
    if not atlas_available:
        fallback_filter: Dict[str, Any] = {
            "destination_id": dest_id,
            "type": {"$in": ["attraction", "tour", "activity"]},
        }
        if indoor_preference is not None:
            fallback_filter["indoor"] = indoor_preference
        if traveler_type in ("family", "couple"):
            audience_val = _TRAVELER_TO_AUDIENCE.get(traveler_type)
            if audience_val:
                fallback_filter["audience"] = audience_val

        try:
            raw_docs = list(
                col.find(fallback_filter).sort("rating", -1).limit(max_candidates)
            )
        except Exception as e:
            logger.error(f"[MongoActivityService] fallback query: {e}")
            return []

    if not raw_docs:
        # Dernier recours : destination seule, toutes activités
        try:
            raw_docs = list(
                col.find({"destination_id": dest_id})
                .sort("rating", -1)
                .limit(max_candidates)
            )
        except Exception as e:
            logger.error(f"[MongoActivityService] final fallback query: {e}")
            return []

    candidates: List[Dict[str, Any]] = []

    for doc in raw_docs:
        tags     = doc.get("tags") or []
        category = doc.get("category") or ""

        # ── COUCHE 2 : scoring ────────────────────────────────────────
        activity_type = doc.get("activity_type") or _infer_activity_type(tags, category)
        price_eur     = doc.get("price_from_eur")

        # Atlas Search score (None si fallback classique)
        search_score = doc.get("search_score") if atlas_available else None

        user_score, matched_criteria = _compute_user_score(
            doc, global_keywords or [], budget_level, traveler_type, beach_score,
            search_score=search_score,
        )
        score = round(USER_SCORE_WEIGHT * user_score + BUSINESS_SCORE_WEIGHT * BUSINESS_SCORE, 4)

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
            "zone":                   doc.get("region") or doc.get("zone"),
            "date":                   None,
            "recurrence_start":       None,
            "recurrence_end":         None,
            "recurrence_days":        [],
            "adult_price":            float(price_eur) if price_eur is not None else 0.0,
            "child_price":            0.0,
            "baby_price":             0.0,
            "currency":               "EUR" if price_eur is not None else "TND",
            "duration_hours":         float(doc["duration_hours"]) if doc.get("duration_hours") is not None else None,
            "max_participants":       0,
            "registered_participants": 0,
            "available_spots":        None,
            "is_available":           None,
            "already_booked":         False,
            "has_geospatial_info":    doc.get("lat") is not None and doc.get("lng") is not None,
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
            "search_score":           round(search_score, 4) if search_score is not None else None,
        })

    candidates.sort(key=lambda x: x["score"], reverse=True)

    logger.info(
        f"[MongoActivityService] {len(candidates[:max_candidates])} candidats | "
        f"destination={destination} | atlas={atlas_available} | raw_docs={len(raw_docs)}"
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
        indoor_preference: Optional[bool] = None,
        beach_score: float = 0.0,
    ) -> List[Dict[str, Any]]:
        return get_candidates(
            destination=destination,
            global_keywords=global_keywords,
            budget_level=budget_level,
            traveler_type=traveler_type,
            max_candidates=max_candidates,
            indoor_preference=indoor_preference,
            beach_score=beach_score,
        )
