from typing import Any, Dict, List

from app.nodes.core.Base_node import BaseNode, NodeConfig


class DataMergerNode(BaseNode):

    MAX_PER_DOMAIN = 5
    MIN_SCORE      = 0.05

    # Domaine prioritaire selon primary_intent
    INTENT_DOMAIN_PRIORITY = {
        "accommodation_recommendation": "hotel",
        "flight_recommendation":        "flight",
        "restaurant_recommendation":    "restaurant",
        "activity_recommendation":      "activity",
        "day_planning":                 "activity",
        "trip_package_recommendation":  None,   # tous égaux
    }

    def __init__(self):
        super().__init__(NodeConfig(name="data_merger", node_type="technical"))

    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:

        # ── 1. LECTURE STATE ─────────────────────────────────────────
        hotel_candidates      = state.get("hotel_candidates")      or []
        flight_candidates     = state.get("flight_candidates")     or []
        restaurant_candidates = state.get("restaurant_candidates") or []
        activity_candidates   = state.get("activity_candidates")   or []

        merged_context  = state.get("merged_context") or {}
        primary_intent  = merged_context.get("primary_intent") or ""

        # ── 2. ENRICHISSEMENT + NORMALISATION PAR DOMAINE ────────────
        domain_map = {
            "hotel":      hotel_candidates,
            "flight":     flight_candidates,
            "restaurant": restaurant_candidates,
            "activity":   activity_candidates,
        }

        buckets: Dict[str, List[Dict]] = {}

        for domain, items in domain_map.items():
            enriched = []
            for c in items:
                candidate = dict(c)
                candidate["domain"]      = domain
                candidate["final_score"] = round(
                    float(c.get("score") or c.get("match_score") or 0.0), 4
                )
                enriched.append(candidate)

            # drop candidats sans valeur
            enriched = [c for c in enriched if c["final_score"] >= self.MIN_SCORE]

            # tri par final_score desc
            enriched.sort(key=lambda x: x["final_score"], reverse=True)

            # trim top-N par domaine
            buckets[domain] = enriched[:self.MAX_PER_DOMAIN]

        # ── 3. FUSION AVEC PRIORITÉ PAR INTENT ───────────────────────
        priority_domain = self.INTENT_DOMAIN_PRIORITY.get(primary_intent)

        candidates: List[Dict] = []

        if priority_domain and priority_domain in buckets:
            candidates.extend(buckets[priority_domain])
            for domain, items in buckets.items():
                if domain != priority_domain:
                    candidates.extend(items)
        else:
            for items in buckets.values():
                candidates.extend(items)

        # ── 4. TRI GLOBAL ─────────────────────────────────────────────
        candidates.sort(key=lambda x: x["final_score"], reverse=True)

        # ── 5. LOG ────────────────────────────────────────────────────
        counts = {d: len(b) for d, b in buckets.items()}
        self.logger.info(
            f"merged={len(candidates)} | "
            f"hotel={counts['hotel']} | "
            f"flight={counts['flight']} | "
            f"restaurant={counts['restaurant']} | "
            f"activity={counts['activity']} | "
            f"priority_domain={priority_domain or 'none'}"
        )

        return {"candidates": candidates}
