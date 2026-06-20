from typing import Any, Dict, List

from app.nodes.core.Base_node import BaseNode, NodeConfig
from app.config.settings import USER_SCORE_WEIGHT, BUSINESS_SCORE_WEIGHT

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
    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:

        candidates: List[Dict] = state.get("candidates") or []

        if not candidates:
            self.logger.info("no candidates to rank")
            return {"ranked_results": [], "total_ranked": 0}

        scored: List[Dict] = []

        for c in candidates:
            candidate = dict(c)

            user_score     = self._user_score(candidate)
            business_score = self._business_score(candidate)

            ranked_score = round(
                USER_SCORE_WEIGHT * user_score
                + BUSINESS_SCORE_WEIGHT * business_score,
                4,
            )

            candidate["user_score"]     = round(user_score, 4)
            candidate["business_score"] = round(business_score, 4)
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
                f"weights=user:{USER_SCORE_WEIGHT} / business:{BUSINESS_SCORE_WEIGHT} | "
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
