import json
from typing import Any, Dict, List, Optional, Set

from app.nodes.core.Base_node import BaseNode, NodeConfig
from app.config.settings import (
    BUSINESS_SCORE_WEIGHT,
    AVAILABILITY_AGENCY_STRONG_THRESHOLD,
    AVAILABILITY_UNKNOWN_FACTOR_PROTECTED,
    AVAILABILITY_UNKNOWN_FACTOR_OPEN,
    INTERACTIONS_REDIS_PREFIX,
    CROSS_SESSION_LIKED_BOOST,
    WEATHER_FACTOR_MIN,
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
    "serpapi":   0.20,
}

_DEFAULT_BUSINESS_SCORE = 0.50
_DEFAULT_USER_SCORE     = 0.50


class RankingNode(BaseNode):

    def __init__(self):
        super().__init__(NodeConfig(name="ranking", node_type="technical"))

    # ─────────────────────────────────────────────────────────────────
    def _load_cross_session_data(self, state: Dict[str, Any]) -> Dict[str, Set[str]]:
        """Lit rejected_types ET liked_types cross-session depuis Redis."""
        empty: Dict[str, Set[str]] = {"rejected": set(), "liked": set()}
        if not _redis:
            return empty
        traveller_id = (
            state.get("travellerId")
            or (state.get("profile_data") or {}).get("id")
        )
        if not traveller_id:
            return empty
        try:
            raw = _redis.get(f"{INTERACTIONS_REDIS_PREFIX}{traveller_id}")
            if raw:
                data = json.loads(raw)
                return {
                    "rejected": set(data.get("rejected_types", [])),
                    "liked":    set(data.get("liked_types",    [])),
                }
        except Exception:
            pass
        return empty

    # ─────────────────────────────────────────────────────────────────
    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:

        candidates: List[Dict] = state.get("candidates") or []

        if not candidates:
            self.logger.info("no candidates to rank")
            return {"ranked_results": [], "total_ranked": 0}

        # ── Contexte météo pour le facteur activités ─────────────────────
        weather_context: Optional[Dict] = state.get("weather_context") or None

        # ── Signaux cross-session (Phase 5) ─────────────────────────────
        cross_session          = self._load_cross_session_data(state)
        cross_session_rejected = cross_session["rejected"]
        cross_session_liked    = cross_session["liked"]
        if cross_session_rejected or cross_session_liked:
            self.logger.info(
                f"[Ranking] cross-session rejected={cross_session_rejected} "
                f"liked={cross_session_liked}"
            )

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

            # Boost soft cross-session : types aimés dans les sessions précédentes.
            # user_score > 0 obligatoire — un candidat non pertinent sur la requête
            # courante ne remonte jamais (invariant V2 multiplicatif préservé).
            # La requête courante reste prioritaire : un score explicite de 0.8
            # bat toujours un score boosted de 0.4 × 1.15 = 0.46.
            if cross_session_liked and user_score > 0:
                activity_type = candidate.get("activity_type", "")
                if activity_type and activity_type in cross_session_liked:
                    user_score = min(1.0, user_score * CROSS_SESSION_LIKED_BOOST)

            business_score = self._business_score(candidate)
            # True=confirmé ×1.0 | None=inconnu ×unknown_factor | False exclu en amont (constraint_validator)
            # Domaines sans champ is_available (hotel, flight, restaurant) → ×1.0 neutre
            avail_factor   = unknown_factor if candidate.get("is_available", True) is None else 1.0

            # Facteur météo : activités outdoor vs indoor selon météo du jour.
            # Neutre (1.0) pour hôtels, vols, restaurants et activités sans type connu.
            weather_f = self._weather_factor(candidate, weather_context)

            # V2 multiplicatif — le business booste les candidats pertinents,
            # ne sauve jamais un candidat non pertinent (user=0 → ranked=0)
            business_boost = (1 + BUSINESS_SCORE_WEIGHT * business_score) / (1 + BUSINESS_SCORE_WEIGHT)
            ranked_score   = round(user_score * business_boost * avail_factor * weather_f, 4)

            candidate["user_score"]          = round(user_score, 4)
            candidate["business_score"]      = round(business_score, 4)
            candidate["availability_factor"] = avail_factor
            candidate["weather_factor"]      = weather_f
            candidate["ranked_score"]        = ranked_score

            scored.append(candidate)

        # tri global par ranked_score desc
        scored.sort(key=lambda x: x["ranked_score"], reverse=True)

        for i, c in enumerate(scored):
            c["rank"] = i + 1

        if scored:
            top = scored[0]
            weather_active = weather_context is not None
            self.logger.info(
                f"ranked={len(scored)} | "
                f"business_weight={BUSINESS_SCORE_WEIGHT} | "
                f"avail_mode={'PROTECTED' if unknown_factor == AVAILABILITY_UNKNOWN_FACTOR_PROTECTED else 'OPEN'} "
                f"(best_confirmed={best_confirmed:.2f}, factor={unknown_factor}) | "
                f"weather={'active' if weather_active else 'off'} | "
                f"#1 [{top.get('domain','?')}] {top.get('name','?')} "
                f"ranked_score={top['ranked_score']} weather_factor={top.get('weather_factor',1.0)}"
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

    @staticmethod
    def _weather_factor(c: Dict, weather_context: Optional[Dict]) -> float:
        """
        Facteur météo [WEATHER_FACTOR_MIN, 1.0] appliqué uniquement aux activités
        dont le type est connu (non "unknown"). Neutre (1.0) pour tous les autres
        domaines (hotel, flight, restaurant) et pour les activités sans type.

        Logique :
          nature / adventure → pondéré par outdoor_score (météo favorable = 1.0, mauvais = WEATHER_FACTOR_MIN)
          culture / relax    → pondéré par indoor_score
          city_experience    → moyenne des deux (polyvalent)
          unknown            → neutre (1.0) — pas de signal fiable
        """
        if c.get("domain") != "activity":
            return 1.0
        activity_type = (c.get("activity_type") or "").strip().lower()
        if not activity_type or activity_type == "unknown":
            return 1.0
        if not weather_context:
            return 1.0
        insights = (weather_context.get("insights") or {})
        outdoor_score = float(insights.get("outdoor_score") or 0.7)
        indoor_score  = float(insights.get("indoor_score")  or 0.7)

        if activity_type in ("nature", "adventure"):
            raw = outdoor_score
        elif activity_type in ("culture", "relax"):
            raw = indoor_score
        elif activity_type == "city_experience":
            raw = (outdoor_score + indoor_score) / 2.0
        else:
            return 1.0

        # Interpolation vers [WEATHER_FACTOR_MIN, 1.0] — jamais éliminatoire
        return round(WEATHER_FACTOR_MIN + (1.0 - WEATHER_FACTOR_MIN) * raw, 4)
