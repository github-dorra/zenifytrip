import json
from typing import Any, Dict, List, Set

from app.nodes.core.Base_node import BaseNode, NodeConfig
from app.config.settings import (
    BUSINESS_SCORE_WEIGHT,
    AVAILABILITY_AGENCY_STRONG_THRESHOLD,
    AVAILABILITY_UNKNOWN_FACTOR_PROTECTED,
    AVAILABILITY_UNKNOWN_FACTOR_OPEN,
    INTERACTIONS_REDIS_PREFIX,
)

try:
    from app.config.redis_config import r as _redis
except Exception:
    _redis = None

# Tier → business_score par défaut quand le candidat n'en a pas un explicite
_TIER_BUSINESS_SCORE: Dict[str, float] = {
    "partner":   0.85,
    "agency":    0.80,
    "internal":  0.80,
    "catalogue": 0.45,
    "external":  0.20,
    "mongodb":   0.20,
}

_DEFAULT_BUSINESS_SCORE = 0.50
_DEFAULT_USER_SCORE     = 0.50


class RankingNode(BaseNode):

    def __init__(self):
        super().__init__(NodeConfig(name="ranking", node_type="technical"))

    # ─────────────────────────────────────────────────────────────────
    def _load_cross_session_rejected(self, state: Dict[str, Any]) -> Set[str]:
        """Lit les types rejetés cross-session depuis Redis. Retourne set vide si indisponible."""
        if not _redis:
            return set()
        traveller_id = (
            state.get("travellerId")
            or (state.get("profile_data") or {}).get("id")
        )
        if not traveller_id:
            return set()
        try:
            raw = _redis.get(f"{INTERACTIONS_REDIS_PREFIX}{traveller_id}")
            if raw:
                data = json.loads(raw)
                return set(data.get("rejected_types", []))
        except Exception:
            pass
        return set()

    # ─────────────────────────────────────────────────────────────────
    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:

        candidates: List[Dict] = state.get("candidates") or []

        if not candidates:
            self.logger.info("no candidates to rank")
            return {"ranked_results": [], "total_ranked": 0}

        # ── Signaux cross-session (Phase 5) ─────────────────────────────
        cross_session_rejected = self._load_cross_session_rejected(state)
        if cross_session_rejected:
            self.logger.info(f"[Ranking] cross-session rejected types: {cross_session_rejected}")

        # ── Pré-passe : facteur dynamique pour dispo inconnue ────────────
        # Force du meilleur candidat CONFIRMÉ (is_available=True — uniquement SOURCE 1 agence)
        best_confirmed = max(
            (self._user_score(c) for c in candidates if c.get("is_available") is True),
            default=0.0,
        )
        unknown_factor = (
            AVAILABILITY_UNKNOWN_FACTOR_PROTECTED
            if best_confirmed >= AVAILABILITY_AGENCY_STRONG_THRESHOLD
            else AVAILABILITY_UNKNOWN_FACTOR_OPEN
        )

        scored: List[Dict] = []

        for c in candidates:
            candidate = dict(c)

            # Activités dont le type a été rejeté cross-session → score nul
            if cross_session_rejected and candidate.get("domain") == "activity":
                activity_type = candidate.get("activity_type", "")
                if activity_type and activity_type in cross_session_rejected:
                    candidate["cross_session_rejected"] = True
                    candidate["user_score"]     = 0.0
                    candidate["business_score"] = self._business_score(candidate)
                    candidate["availability_factor"] = 1.0
                    candidate["ranked_score"]   = 0.0
                    scored.append(candidate)
                    continue

            user_score     = self._user_score(candidate)
            business_score = self._business_score(candidate)
            # True=confirmé ×1.0 | None=inconnu ×unknown_factor | False exclu en amont (constraint_validator)
            # Domaines sans champ is_available (hotel, flight, restaurant) → ×1.0 neutre
            avail_factor   = unknown_factor if candidate.get("is_available", True) is None else 1.0

            # V2 multiplicatif — le business booste les candidats pertinents,
            # ne sauve jamais un candidat non pertinent (user=0 → ranked=0)
            business_boost = (1 + BUSINESS_SCORE_WEIGHT * business_score) / (1 + BUSINESS_SCORE_WEIGHT)
            ranked_score   = round(user_score * business_boost * avail_factor, 4)

            candidate["user_score"]     = round(user_score, 4)
            candidate["business_score"] = round(business_score, 4)
            candidate["availability_factor"] = avail_factor
            candidate["ranked_score"]   = ranked_score

            scored.append(candidate)

        # tri global par ranked_score desc
        scored.sort(key=lambda x: x["ranked_score"], reverse=True)

        for i, c in enumerate(scored):
            c["rank"] = i + 1

        if scored:
            top = scored[0]
            self.logger.info(
                f"ranked={len(scored)} | "
                f"business_weight={BUSINESS_SCORE_WEIGHT} | "
                f"avail_mode={'PROTECTED' if unknown_factor == AVAILABILITY_UNKNOWN_FACTOR_PROTECTED else 'OPEN'} "
                f"(best_confirmed={best_confirmed:.2f}, factor={unknown_factor}) | "
                f"#1 [{top.get('domain','?')}] {top.get('name','?')} "
                f"ranked_score={top['ranked_score']}"
            )

        return {
            "ranked_results": scored,
            "total_ranked":   len(scored),
        }

    # ─────────────────────────────────────────────────────────────────
    # Helpers d'extraction de score
    # ─────────────────────────────────────────────────────────────────

    def _user_score(self, c: Dict) -> float:
        for key in ("user_score", "match_score", "final_score", "score"):
            v = c.get(key)
            if v is not None:
                try:
                    return max(0.0, min(float(v), 1.0))
                except (ValueError, TypeError):
                    pass
        return _DEFAULT_USER_SCORE

    def _business_score(self, c: Dict) -> float:
        # priorité 1 : champ explicite
        v = c.get("business_score")
        if v is not None:
            try:
                return max(0.0, min(float(v), 1.0))
            except (ValueError, TypeError):
                pass

        # priorité 2 : tier ou source du candidat
        for key in ("tier", "source"):
            label = str(c.get(key, "")).strip().lower()
            if label in _TIER_BUSINESS_SCORE:
                return _TIER_BUSINESS_SCORE[label]

        return _DEFAULT_BUSINESS_SCORE
