import logging
import requests
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple

from app.config.settings import ACTIVITIES_API_URL, BOOKINGS_API_URL, API_KEY, USER_SCORE_WEIGHT, BUSINESS_SCORE_WEIGHT
from app.services.cache_service import SimpleTTLCache, cache

logger = logging.getLogger(__name__)


class ActivityService:

    HEADERS = {"Authorization": f"Bearer {API_KEY}"}
    TIMEOUT = 30

    # Prix adulte par tranche de budget (TND)
    BUDGET_TO_PRICE: Dict[str, Tuple[float, float]] = {
        "low":     (0,    40),
        "medium":  (40,  120),
        "luxury":  (120, 9999),
        "premium": (120, 9999),
    }

    # Mots-clés par type de voyageur pour le matching de nom
    TRAVELER_TYPE_KEYWORDS: Dict[str, List[str]] = {
        "family":  ["famille", "enfant", "kids", "family", "water park", "parc", "aqua"],
        "couple":  ["romantique", "romantic", "soirée", "sunset", "dîner", "couples", "spa"],
        "solo":    ["aventure", "adventure", "randonnée", "hiking", "solo", "quad", "surf"],
    }

    # =========================================================
    # COUCHE D'ACCÈS BRUTE — fetch + cache
    # =========================================================

    @staticmethod
    def get_all_bookings() -> List[Dict[str, Any]]:
        """
        Retourne tous les bookings depuis /api/bookings — mis en cache 24h.
        Volume connu : ~141 entrées → take=200 suffit en un seul appel.
        """
        cached = cache.get("bookings_all")
        if cached is not None:
            return cached

        all_bookings: List[Dict[str, Any]] = []
        try:
            response = requests.get(
                BOOKINGS_API_URL,
                headers=ActivityService.HEADERS,
                params={"take": 200, "skip": 0},
                timeout=ActivityService.TIMEOUT,
            )
            response.raise_for_status()
            all_bookings = response.json().get("results", [])
        except Exception as e:
            logger.error(f"[ActivityService] get_all_bookings: {e}")

        cache.set("bookings_all", all_bookings, SimpleTTLCache.TTL_ACTIVITIES)
        return all_bookings

    @staticmethod
    def get_activity_by_id(activity_id: str) -> Optional[Dict[str, Any]]:
        """
        Retourne le détail d'une activité depuis /api/activities/{id} — mis en cache 24h.
        Retourne None si l'API échoue (404, 500, timeout).
        """
        if not activity_id:
            return None

        cache_key = f"activity_{activity_id}"
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

        try:
            response = requests.get(
                f"{ACTIVITIES_API_URL}/{activity_id}",
                headers=ActivityService.HEADERS,
                timeout=ActivityService.TIMEOUT,
            )
            response.raise_for_status()
            activity = response.json()
            if activity:
                cache.set(cache_key, activity, SimpleTTLCache.TTL_ACTIVITIES)
            return activity
        except Exception as e:
            logger.warning(f"[ActivityService] get_activity_by_id [{activity_id}]: {e}")
            return None

    # =========================================================
    # LOGIQUE MÉTIER
    # =========================================================

    @staticmethod
    def get_traveller_booked_activity_ids(traveller_id: str) -> Set[str]:
        """Retourne les activityIds déjà réservés par ce voyageur (status != Cancelled)."""
        if not traveller_id:
            return set()

        return {
            str(b["activityId"])
            for b in ActivityService.get_all_bookings()
            if str(b.get("travellerId", "")) == str(traveller_id)
            and b.get("status") != "Cancelled"
            and b.get("activityId")
        }

    @staticmethod
    def _is_available(activity: Dict[str, Any], request_date: Optional[str]) -> bool:
        """Vérifie si l'activité a des places disponibles et est dans la plage de dates."""
        max_p = activity.get("maxParticipants") or 0
        reg_p = activity.get("registeredParticipants") or 0

        if max_p > 0 and reg_p >= max_p:
            return False

        if request_date:
            try:
                req_dt = datetime.fromisoformat(request_date[:10])
                rec_start = activity.get("recurrenceStart")
                rec_end   = activity.get("recurrenceEnd")
                if rec_start and rec_end:
                    if not (
                        datetime.fromisoformat(rec_start[:10])
                        <= req_dt <=
                        datetime.fromisoformat(rec_end[:10])
                    ):
                        return False
            except (ValueError, TypeError):
                pass

        return True

    @staticmethod
    def _compute_business_score(tier: str) -> float:
        """
        Score commercial — aligné sur le pattern hotel_node.
          agency    → 1.0  (excursion vendue par l'agence, marge maximale)
          external  → 0.3  (source externe, pas de marge directe)
        """
        return 1.0 if tier == "agency" else 0.3

    @staticmethod
    def _compute_user_score(
        activity: Dict[str, Any],
        global_keywords: List[str],
        budget_level: Optional[str],
        traveler_type: Optional[str],
    ) -> Tuple[float, List[str]]:
        """
        Score utilisateur entre 0.0 et 1.0.

        Répartition :
          Keyword match dans le nom   0.35
          Places disponibles          0.25
          Budget (prix adulte)        0.20
          Type de voyageur            0.20
        """
        s: float = 0.0
        criteria: List[str] = []
        name_lower = (activity.get("name") or "").lower()

        # Keyword match (0.35)
        if global_keywords:
            matched = [kw for kw in global_keywords if kw.lower() in name_lower]
            if matched:
                ratio = len(matched) / len(global_keywords)
                s += round(min(0.35, ratio * 0.35), 4)
                criteria.append("keyword_match")

        # Places disponibles (0.25)
        max_p = activity.get("maxParticipants") or 0
        reg_p = activity.get("registeredParticipants") or 0
        if max_p > 0:
            avail_ratio = max(0.0, (max_p - reg_p) / max_p)
            s += round(0.25 * avail_ratio, 4)
            if avail_ratio > 0.2:
                criteria.append("spots_available")

        # Budget (0.20)
        adult_price = float(activity.get("adultPrice") or 0)
        if budget_level and adult_price > 0:
            lo, hi = ActivityService.BUDGET_TO_PRICE.get(budget_level, (0, 9999))
            if lo <= adult_price <= hi:
                s += 0.20
                criteria.append("budget_match")

        # Type de voyageur (0.20)
        if traveler_type:
            type_kws = ActivityService.TRAVELER_TYPE_KEYWORDS.get(traveler_type, [])
            if any(kw in name_lower for kw in type_kws):
                s += 0.20
                criteria.append("traveler_type_match")

        return round(min(s, 1.0), 4), criteria

    @staticmethod
    def _build_unique_bookings(
        all_bookings: List[Dict[str, Any]],
        destination: Optional[str],
    ) -> Dict[str, Dict[str, Any]]:
        """
        Déduplique les bookings par activityId (garde le premier trouvé).
        Filtre par destination via referenceContactHotelName si fournie.
        Ignore les bookings Cancelled et sans activityId.
        """
        bookings_by_activity: Dict[str, Dict[str, Any]] = {}

        for booking in all_bookings:
            if booking.get("status") == "Cancelled":
                continue
            activity_id = booking.get("activityId")
            if not activity_id:
                continue
            activity_id = str(activity_id)
            if activity_id not in bookings_by_activity:
                bookings_by_activity[activity_id] = booking

        # Filtre destination sur le nom de l'hôtel de référence
        if destination and bookings_by_activity:
            dest_lower = destination.lower()
            filtered = {
                aid: bk
                for aid, bk in bookings_by_activity.items()
                if dest_lower in (bk.get("referenceContactHotelName") or "").lower()
                or not bk.get("referenceContactHotelName")
            }
            # Fallback si le filtre vide tout — destination inconnue dans les bookings
            if filtered:
                bookings_by_activity = filtered

        return bookings_by_activity

    # =========================================================
    # POINT D'ENTRÉE PRINCIPAL
    # =========================================================

    @staticmethod
    def get_activity_candidates(
        traveller_id: Optional[str],
        destination: Optional[str],
        global_keywords: List[str],
        budget_level: Optional[str],
        traveler_type: Optional[str],
        start_date: Optional[str],
        max_candidates: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        Retourne les candidats activités depuis l'API interne agence.

        Score final = 0.7 * user_score + 0.3 * business_score
        (aligné sur le pattern hotel_node — toutes les activités internes ont business_score=1.0)

        Flux :
          /api/bookings (cache 24h)
            → déduplication par activityId + filtre destination
            → /api/activities/{id} (cache 24h par activité)
            → scoring 70/30 + tri
            → top max_candidates
        """
        all_bookings = ActivityService.get_all_bookings()
        if not all_bookings:
            logger.warning("[ActivityService] bookings vides — API indisponible ou cache vide")
            return []

        already_booked_ids: Set[str] = (
            ActivityService.get_traveller_booked_activity_ids(traveller_id)
            if traveller_id else set()
        )

        bookings_by_activity = ActivityService._build_unique_bookings(all_bookings, destination)
        if not bookings_by_activity:
            return []

        candidates: List[Dict[str, Any]] = []

        for activity_id, booking in bookings_by_activity.items():
            activity = ActivityService.get_activity_by_id(activity_id)
            if not activity:
                continue

            tier            = "agency"
            is_available    = ActivityService._is_available(activity, start_date)
            business_score  = ActivityService._compute_business_score(tier)
            user_score, matched_criteria = ActivityService._compute_user_score(
                activity=activity,
                global_keywords=global_keywords or [],
                budget_level=budget_level,
                traveler_type=traveler_type,
            )
            score = round(USER_SCORE_WEIGHT * user_score + BUSINESS_SCORE_WEIGHT * business_score, 4)

            max_p = activity.get("maxParticipants") or 0
            reg_p = activity.get("registeredParticipants") or 0

            candidates.append({
                # Identification
                "id":                      activity_id,
                "name":                    activity.get("name") or "",
                "description":             None,
                # Provenance
                "source":                  "internal",
                "tier":                    tier,
                "activity_id":             activity_id,
                "booking_reference":       str(booking.get("id") or ""),
                "hotel_name":              booking.get("referenceContactHotelName"),
                # Dates
                "date":                    booking.get("date") or activity.get("outboundDate"),
                "recurrence_start":        activity.get("recurrenceStart"),
                "recurrence_end":          activity.get("recurrenceEnd"),
                "recurrence_days":         activity.get("recurrenceWeekDays") or [],
                # Tarifs
                "adult_price":             float(activity.get("adultPrice") or 0),
                "child_price":             float(activity.get("childPrice") or 0),
                "baby_price":              float(activity.get("babyPrice") or 0),
                "currency":                activity.get("currency") or booking.get("currency") or "TND",
                # Disponibilité
                "max_participants":        max_p,
                "registered_participants": reg_p,
                "available_spots":         max(0, max_p - reg_p) if max_p > 0 else None,
                "is_available":            is_available,
                "already_booked":          activity_id in already_booked_ids,
                # Scoring — aligné sur hotel_node (score / business_score / user_score)
                "score":                   score,
                "business_score":          round(business_score, 4),
                "user_score":              round(user_score, 4),
                "matched_criteria":        matched_criteria,
                "recommendation_reason":   None,   # rempli par ranking_node
            })

        # Tri : disponibles en premier, puis score décroissant
        candidates.sort(
            key=lambda x: (int(x["is_available"]), x["score"]),
            reverse=True,
        )

        logger.info(
            f"[ActivityService] {len(candidates)} candidats | "
            f"destination={destination} | already_booked={len(already_booked_ids)}"
        )

        return candidates[:max_candidates]
