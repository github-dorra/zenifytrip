"""
ActivityNode — Phase 4 recommandation activités
================================================
SOURCE 1 : catalogue agence (/api/bookings → /api/activities/{id})
SOURCE 2 : MongoDB Atlas (scraper TripAdvisor par ville)

Les deux sources tournent en parallèle via ThreadPoolExecutor.
Déduplication cross-source via rapidfuzz (seuil 75).
score = 0.7 * user_score + 0.3 * business_score
"""
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError
from typing import Any, Dict, List, Optional

from app.nodes.core.Base_node import BaseNode, NodeConfig
from app.schemas.activity_schema import ActivityCandidate, ActivityNodeOutput
from app.services.activity_service import InternalActivityService, MongoActivityService

logger = logging.getLogger(__name__)

MAX_PER_SOURCE   = 10
MAX_FINAL        = 12
DEDUP_THRESHOLD  = 75   # rapidfuzz ratio — noms très similaires = doublon
FETCH_TIMEOUT_S  = 15


class ActivityNode(BaseNode):

    def __init__(self):
        super().__init__(
            NodeConfig(
                name="activity_node",
                node_type="technical",
            )
        )

    # =========================================================
    # EXTRACTION STATE
    # =========================================================

    @staticmethod
    def _extract_params(state: Dict[str, Any]) -> Dict[str, Any]:
        """Extrait les paramètres nécessaires depuis GraphState."""
        merged      = state.get("merged_context") or {}
        intent      = state.get("intent_result")  or {}
        constraints = intent.get("constraints")   or {}

        destination  = merged.get("destination") or constraints.get("destination") or ""
        start_date   = merged.get("start_date")  or constraints.get("start_date")
        budget_level = merged.get("budget_level") or constraints.get("budget_level")

        profile      = state.get("profile_data") or {}
        traveller_id = state.get("travellerId")  or profile.get("id") or ""

        traveler_type = ActivityNode._infer_traveler_type(profile)

        # Keywords : global (semantic_node) + contextuel (semantic_node) fusionnés sans doublon
        global_keywords     = state.get("global_keywords")     or merged.get("global_keywords") or []
        contextual_keywords = state.get("contextual_keywords") or []
        all_keywords = list(dict.fromkeys(global_keywords + contextual_keywords))

        # Signaux météo — produits par weather_node, lus ici, jamais recalculés
        insights      = (state.get("weather_context") or {}).get("insights") or {}
        indoor_score  = insights.get("indoor_score")
        outdoor_score = insights.get("outdoor_score")
        indoor_preference = (
            (indoor_score > outdoor_score)
            if indoor_score is not None and outdoor_score is not None
            else None
        )
        beach_score = float(insights.get("beach_score") or 0)

        return {
            "traveller_id":      str(traveller_id) if traveller_id else "",
            "destination":       destination,
            "all_keywords":      all_keywords,
            "budget_level":      budget_level,
            "traveler_type":     traveler_type,
            "start_date":        start_date,
            "indoor_preference": indoor_preference,
            "beach_score":       beach_score,
        }

    @staticmethod
    def _infer_traveler_type(profile: Dict[str, Any]) -> Optional[str]:
        """Déduit le profil voyageur depuis les données profil."""
        has_partner = profile.get("hasPartner", False)
        child_count = int(profile.get("childCount") or 0)
        baby_count  = int(profile.get("babyCount")  or 0)

        if child_count > 0 or baby_count > 0:
            return "family"
        if has_partner:
            return "couple"
        return "solo"

    # =========================================================
    # DÉDUPLICATION CROSS-SOURCE
    # =========================================================

    @staticmethod
    def _dedup(
        source1: List[Dict[str, Any]],
        source2: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """
        Fusionne SOURCE 1 et SOURCE 2 en éliminant les doublons par nom (rapidfuzz).
        SOURCE 1 (agence) prime toujours en cas de doublon.
        """
        try:
            from rapidfuzz import fuzz
            use_fuzzy = True
        except ImportError:
            logger.warning("[ActivityNode] rapidfuzz absent — dédup exacte uniquement")
            use_fuzzy = False

        merged: List[Dict[str, Any]] = list(source1)
        names_s1 = [c.get("name", "").lower() for c in source1]

        for candidate in source2:
            name = (candidate.get("name") or "").lower()
            if not name:
                merged.append(candidate)
                continue

            is_dup = False
            if use_fuzzy:
                for existing_name in names_s1:
                    if fuzz.ratio(name, existing_name) >= DEDUP_THRESHOLD:
                        is_dup = True
                        break
            else:
                is_dup = name in names_s1

            if not is_dup:
                merged.append(candidate)

        return merged

    # =========================================================
    # VALIDATION PYDANTIC
    # =========================================================

    @staticmethod
    def _validate(raw_candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Valide chaque candidat via ActivityCandidate — élimine les invalides."""
        valid = []
        for raw in raw_candidates:
            try:
                valid.append(ActivityCandidate(**raw).model_dump())
            except Exception as e:
                logger.warning(f"[ActivityNode] candidat invalide ignoré: {e} | {raw.get('name')}")
        return valid

    # =========================================================
    # RUN
    # =========================================================

    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        params = self._extract_params(state)

        destination       = params["destination"]
        traveller_id      = params["traveller_id"]
        all_kws           = params["all_keywords"]
        budget            = params["budget_level"]
        traveler_type     = params["traveler_type"]
        start_date        = params["start_date"]
        indoor_preference = params["indoor_preference"]
        beach_score       = params["beach_score"]

        self.logger.info(
            f"[ActivityNode] destination={destination!r} | "
            f"keywords={all_kws} | indoor={indoor_preference} | beach={beach_score:.2f} | "
            f"budget={budget} | traveler_type={traveler_type}"
        )

        source1_result: List[Dict[str, Any]] = []
        source2_result: List[Dict[str, Any]] = []

        # ── Appels parallèles SOURCE 1 + SOURCE 2 ─────────────────────
        def fetch_source1():
            return InternalActivityService.get_candidates(
                traveller_id=traveller_id,
                destination=destination,
                global_keywords=all_kws,
                budget_level=budget,
                traveler_type=traveler_type,
                start_date=start_date,
                max_candidates=MAX_PER_SOURCE,
            )

        def fetch_source2():
            return MongoActivityService.get_candidates(
                destination=destination,
                global_keywords=all_kws,
                budget_level=budget,
                traveler_type=traveler_type,
                max_candidates=MAX_PER_SOURCE,
                indoor_preference=indoor_preference,
                beach_score=beach_score,
            )

        futures_map = {}
        try:
            with ThreadPoolExecutor(max_workers=2) as executor:
                futures_map = {
                    executor.submit(fetch_source1): "source1",
                    executor.submit(fetch_source2): "source2",
                }
                for future in as_completed(futures_map, timeout=FETCH_TIMEOUT_S):
                    label = futures_map[future]
                    try:
                        result = future.result()
                        if label == "source1":
                            source1_result = result or []
                        else:
                            source2_result = result or []
                    except Exception as e:
                        self.logger.error(f"[ActivityNode] {label} erreur: {e}")
        except TimeoutError:
            self.logger.error("[ActivityNode] timeout fetch sources")
        except Exception as e:
            self.logger.error(f"[ActivityNode] ThreadPoolExecutor: {e}")

        self.logger.info(
            f"[ActivityNode] brut — source1={len(source1_result)} | source2={len(source2_result)}"
        )

        # ── Déduplication + fusion ─────────────────────────────────────
        merged = self._dedup(source1_result, source2_result)

        # ── Tri final par score ────────────────────────────────────────
        # True (confirmé) > None (inconnu) > False (indisponible — exclu au ranking)
        _avail_rank = {True: 2, None: 1, False: 0}
        merged.sort(key=lambda x: (_avail_rank.get(x.get("is_available"), 1), x.get("score", 0)), reverse=True)

        # ── Validation Pydantic ────────────────────────────────────────
        validated = self._validate(merged[:MAX_FINAL])

        # ── Confiance ─────────────────────────────────────────────────
        if len(validated) >= 6:
            confidence = 0.9
        elif len(validated) >= 3:
            confidence = 0.7
        elif len(validated) > 0:
            confidence = 0.5
        else:
            confidence = 0.0

        self.logger.info(
            f"[ActivityNode] {len(validated)} candidats validés | confidence={confidence}"
        )

        # Retourner la liste de dicts (model_dump déjà appelé dans _validate)
        # Ne PAS passer par ActivityNodeOutput.activity_candidates — reconvertirait en objets Pydantic
        return {"activity_candidates": validated}
