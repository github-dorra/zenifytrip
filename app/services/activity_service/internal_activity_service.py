"""
SOURCE 1 — Catalogue agence
Excursions proposées par l'agence via /api/bookings → /api/activities/{id}.
business_score = 0.8 (vendable, commission agence)
"""
import logging
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple

from app.config.settings import ACTIVITIES_API_URL, BOOKINGS_API_URL, API_KEY, USER_SCORE_WEIGHT, BUSINESS_SCORE_WEIGHT
from app.services.activity_service.scoring import budget_proximity_score
from app.services.cache_service import SimpleTTLCache, cache

logger = logging.getLogger(__name__)


class InternalActivityService:

    HEADERS = {"Authorization": f"Bearer {API_KEY}"}
    TIMEOUT = 30
    BUSINESS_SCORE = 0.7   # catalogue agence — commission sur vente

    BUDGET_TO_PRICE: Dict[str, Tuple[float, float]] = {
        "low":     (0,    40),
        "medium":  (40,  120),
        "luxury":  (120, 9999),
        "premium": (120, 9999),
    }

    TRAVELER_TYPE_KEYWORDS: Dict[str, List[str]] = {
        "family":  ["famille", "enfant", "kids", "family", "water park", "parc", "aqua"],
        "couple":  ["romantique", "romantic", "soirée", "sunset", "dîner", "couples", "spa"],
        "solo":    ["aventure", "adventure", "randonnée", "hiking", "solo", "quad", "surf"],
    }

    ACTIVITY_TYPE_KEYWORDS: Dict[str, List[str]] = {
        "culture":         ["musée", "museum", "ribat", "médina", "mosquée", "synagogue",
                            "ruines", "patrimoine", "historique", "monument", "archéologique"],
        "nature":          ["plage", "mer", "lac", "oasis", "forêt", "parc", "montagne",
                            "sahara", "désert", "dune", "nature"],
        "adventure":       ["safari", "quad", "plongée", "surf", "randonnée", "kite",
                            "escalade", "4x4", "jet ski", "parachute"],
        "relax":           ["spa", "hammam", "thalasso", "détente", "repos", "golf",
                            "massage", "bien-être"],
        "city_experience": ["souk", "marché", "shopping", "médina", "balade", "marina",
                            "ville", "port", "promenade"],
    }

    # =========================================================
    # FETCH BRUT — /api/bookings + /api/activities/{id}
    # =========================================================

    @staticmethod
    def get_all_bookings() -> List[Dict[str, Any]]:
        """Tous les bookings agence — cache 24h. ~141 entrées, take=200."""
        cached = cache.get("bookings_all")
        if cached is not None:
            return cached

        all_bookings: List[Dict[str, Any]] = []
        try:
            response = requests.get(
                BOOKINGS_API_URL,
                headers=InternalActivityService.HEADERS,
                params={"take": 200, "skip": 0},
                timeout=InternalActivityService.TIMEOUT,
            )
            response.raise_for_status()
            all_bookings = response.json().get("results", [])
        except Exception as e:
            logger.error(f"[InternalActivityService] get_all_bookings: {e}")

        cache.set("bookings_all", all_bookings, SimpleTTLCache.TTL_ACTIVITIES)
        return all_bookings

    @staticmethod
    def pre_warm_cache() -> None:
        """
        Boot-time pre-warm — à appeler dans un thread daemon au démarrage.
        Charge bookings_all + tous les activity_{id} en parallèle → cold cache
        éliminé sur la 1ère requête utilisateur réelle (~4.5s → ~0ms).
        """
        logger.info("[InternalActivityService] pre-warm démarré")
        try:
            bookings = InternalActivityService.get_all_bookings()
            if not bookings:
                logger.info("[InternalActivityService] pre-warm: aucun booking disponible")
                return

            unique_ids = list({
                str(b["activityId"])
                for b in bookings
                if b.get("activityId") and b.get("status") != "Cancelled"
            })
            logger.info(
                f"[InternalActivityService] pre-warm: {len(unique_ids)} activityIds à charger"
            )

            fetched = 0
            n_workers = min(len(unique_ids), 40)
            with ThreadPoolExecutor(max_workers=n_workers) as pool:
                future_to_id = {
                    pool.submit(InternalActivityService.get_activity_by_id, aid): aid
                    for aid in unique_ids
                }
                for fut in as_completed(future_to_id, timeout=60):
                    aid = future_to_id[fut]
                    try:
                        if fut.result():
                            fetched += 1
                    except Exception as exc:
                        logger.warning(f"[InternalActivityService] pre-warm {aid}: {exc}")

            logger.info(
                f"[InternalActivityService] pre-warm terminé: "
                f"{fetched}/{len(unique_ids)} activities en cache"
            )
        except Exception as e:
            logger.warning(f"[InternalActivityService] pre-warm échoué (non bloquant): {e}")

    @staticmethod
    def get_activity_by_id(activity_id: str) -> Optional[Dict[str, Any]]:
        """Détail activité /api/activities/{id} — cache 24h par activité."""
        if not activity_id:
            return None

        cache_key = f"activity_{activity_id}"
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

        try:
            response = requests.get(
                f"{ACTIVITIES_API_URL}/{activity_id}",
                headers=InternalActivityService.HEADERS,
                timeout=InternalActivityService.TIMEOUT,
            )
            response.raise_for_status()
            activity = response.json()
            if activity:
                cache.set(cache_key, activity, SimpleTTLCache.TTL_ACTIVITIES)
            return activity
        except Exception as e:
            logger.warning(f"[InternalActivityService] get_activity_by_id [{activity_id}]: {e}")
            return None

    # =========================================================
    # LOGIQUE MÉTIER
    # =========================================================

    @staticmethod
    def get_traveller_booked_activity_ids(traveller_id: str) -> Set[str]:
        """activityIds déjà réservés par ce voyageur (status != Cancelled)."""
        if not traveller_id:
            return set()
        return {
            str(b["activityId"])
            for b in InternalActivityService.get_all_bookings()
            if str(b.get("travellerId", "")) == str(traveller_id)
            and b.get("status") != "Cancelled"
            and b.get("activityId")
        }

    @staticmethod
    def _infer_activity_type(name: str) -> str:
        """Macro-catégorie rule-based depuis le nom — fallback 'unknown'."""
        name_lower = name.lower()
        for activity_type, keywords in InternalActivityService.ACTIVITY_TYPE_KEYWORDS.items():
            if any(kw in name_lower for kw in keywords):
                return activity_type
        return "unknown"

    @staticmethod
    def _is_available(activity: Dict[str, Any], request_date: Optional[str]) -> bool:
        """Places disponibles + date dans la plage de récurrence."""
        max_p = activity.get("maxParticipants") or 0
        reg_p = activity.get("registeredParticipants") or 0
        if max_p > 0 and reg_p >= max_p:
            return False
        if request_date:
            try:
                req_dt    = datetime.fromisoformat(request_date[:10])
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
    def _compute_user_score(
        activity: Dict[str, Any],
        global_keywords: List[str],
        budget_level: Optional[str],
        traveler_type: Optional[str],
    ) -> Tuple[float, List[str]]:
        """
        user_score 0.0→1.0
          keyword match    0.35
          places dispo     0.25
          budget           0.20
          traveler type    0.20
        """
        s: float = 0.0
        criteria: List[str] = []
        name_lower = (activity.get("name") or "").lower()

        if global_keywords:
            matched = [kw for kw in global_keywords if kw.lower() in name_lower]
            if matched:
                s += round(min(0.35, len(matched) / len(global_keywords) * 0.35), 4)
                criteria.append("keyword_match")

        max_p = activity.get("maxParticipants") or 0
        reg_p = activity.get("registeredParticipants") or 0
        if max_p > 0:
            avail_ratio = max(0.0, (max_p - reg_p) / max_p)
            s += round(0.25 * avail_ratio, 4)
            if avail_ratio > 0.2:
                criteria.append("spots_available")

        adult_price = float(activity.get("adultPrice") or 0)
        if budget_level and adult_price > 0:
            b = budget_proximity_score(adult_price, budget_level, InternalActivityService.BUDGET_TO_PRICE)
            s += b
            if b >= 0.15:
                criteria.append("budget_match")
            elif b > 0:
                criteria.append("budget_partial")

        if traveler_type:
            type_kws = InternalActivityService.TRAVELER_TYPE_KEYWORDS.get(traveler_type, [])
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
        Déduplique par activityId, filtre Cancelled.
        Filtre destination via referenceContactHotelName avec fallback.
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

        if destination and bookings_by_activity:
            dest_lower = destination.lower()
            filtered = {
                aid: bk for aid, bk in bookings_by_activity.items()
                if dest_lower in (bk.get("referenceContactHotelName") or "").lower()
                or not bk.get("referenceContactHotelName")
            }
            if filtered:
                bookings_by_activity = filtered

        return bookings_by_activity

    # =========================================================
    # POINT D'ENTRÉE
    # =========================================================

    @staticmethod
    def get_candidates(
        traveller_id: Optional[str],
        destination: Optional[str],
        global_keywords: List[str],
        budget_level: Optional[str],
        traveler_type: Optional[str],
        start_date: Optional[str],
        max_candidates: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        Retourne les candidats SOURCE 1 (catalogue agence).
        score = 0.7 * user_score + 0.3 * 0.8
        """
        all_bookings = InternalActivityService.get_all_bookings()
        if not all_bookings:
            return []

        already_booked_ids: Set[str] = (
            InternalActivityService.get_traveller_booked_activity_ids(traveller_id)
            if traveller_id else set()
        )

        bookings_by_activity = InternalActivityService._build_unique_bookings(
            all_bookings, destination
        )
        if not bookings_by_activity:
            return []

        # Fetch toutes les activités en parallèle — évite le N+1 séquentiel.
        # max_workers = nb d'IDs (plafonné à 40) : tous les appels partent
        # simultanément → cold cache = max(latence_api) au lieu de N × latence_api.
        fetched: Dict[str, Dict[str, Any]] = {}
        n_workers = min(len(bookings_by_activity), 40)
        with ThreadPoolExecutor(max_workers=n_workers) as _pool:
            future_to_id = {
                _pool.submit(InternalActivityService.get_activity_by_id, aid): aid
                for aid in bookings_by_activity
            }
            for fut in as_completed(future_to_id, timeout=12):
                aid = future_to_id[fut]
                try:
                    result = fut.result()
                    if result:
                        fetched[aid] = result
                except Exception as exc:
                    logger.warning(f"[InternalActivityService] fetch {aid}: {exc}")

        candidates: List[Dict[str, Any]] = []

        for activity_id, booking in bookings_by_activity.items():
            activity = fetched.get(activity_id)
            if not activity:
                continue

            is_available = InternalActivityService._is_available(activity, start_date)
            user_score, matched_criteria = InternalActivityService._compute_user_score(
                activity, global_keywords or [], budget_level, traveler_type
            )
            business_score = InternalActivityService.BUSINESS_SCORE
            score = round(USER_SCORE_WEIGHT * user_score + BUSINESS_SCORE_WEIGHT * business_score, 4)

            max_p = activity.get("maxParticipants") or 0
            reg_p = activity.get("registeredParticipants") or 0

            candidates.append({
                "id":                      activity_id,
                "name":                    activity.get("name") or "",
                "description":             None,
                "activity_type":           InternalActivityService._infer_activity_type(
                                               activity.get("name") or ""
                                           ),
                "source":                  "internal",
                "tier":                    "agency",
                "activity_id":             activity_id,
                "booking_reference":       str(booking.get("id") or ""),
                "hotel_name":              booking.get("referenceContactHotelName"),
                "destination":             destination or "",
                "zone":                    None,
                "date":                    booking.get("date") or activity.get("outboundDate"),
                "recurrence_start":        activity.get("recurrenceStart"),
                "recurrence_end":          activity.get("recurrenceEnd"),
                "recurrence_days":         activity.get("recurrenceWeekDays") or [],
                "adult_price":             float(activity.get("adultPrice") or 0),
                "child_price":             float(activity.get("childPrice") or 0),
                "baby_price":              float(activity.get("babyPrice") or 0),
                "currency":                activity.get("currency") or booking.get("currency") or "TND",
                "duration_hours":          None,
                "max_participants":        max_p,
                "registered_participants": reg_p,
                "available_spots":         max(0, max_p - reg_p) if max_p > 0 else None,
                "is_available":            is_available,
                "already_booked":          activity_id in already_booked_ids,
                "has_geospatial_info":     False,
                "distance_km":             None,
                "travel_time_min":         None,
                "score":                   score,
                "business_score":          round(business_score, 4),
                "user_score":              round(user_score, 4),
                "matched_criteria":        matched_criteria,
                "semantic_tags":           [],
                "recommendation_context":  "excursion_agence",
                "recommendation_reason":   None,
            })

        candidates.sort(key=lambda x: (int(x["is_available"]), x["score"]), reverse=True)

        logger.info(
            f"[InternalActivityService] {len(candidates)} candidats | "
            f"destination={destination} | already_booked={len(already_booked_ids)}"
        )
        return candidates[:max_candidates]
