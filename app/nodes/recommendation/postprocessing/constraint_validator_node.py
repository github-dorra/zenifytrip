from typing import Any, Dict, List

from app.nodes.core.Base_node import BaseNode, NodeConfig


# Budget → price_level max autorisé (restaurants, échelle Google Places 0–4)
_BUDGET_PRICE_LEVEL: Dict[str, int] = {
    "low":    1,
    "medium": 3,
    # luxury | premium : pas de plafond → absent du dict, tous candidats passent
}

# Conversion price_level string ("$" … "$$$$") → entier 1–4
_PRICE_LEVEL_STR_TO_INT: Dict[str, int] = {
    "$":    1,
    "$$":   2,
    "$$$":  3,
    "$$$$": 4,
}

# Budget → adult_price max autorisé (activités, en TND)
_BUDGET_MAX_ACTIVITY_TND: Dict[str, float] = {
    "low":    60.0,
    "medium": 200.0,
    # luxury | premium : pas de plafond
}


class ConstraintValidatorNode(BaseNode):
    """
    Filtre la liste `candidates` (produite par data_merger) selon les contraintes dures.

    Règles appliquées dans l'ordre :
      1. Activité déjà réservée par ce voyageur       → filtre dur, tous modes
      2. is_available=False (capacité épuisée OU hors récurrence) → filtre dur, tous domaines
         is_available=None (dispo inconnue, ex. SOURCE 2 MongoDB) → conservé, présenté "à confirmer"
      3. Budget restaurant (price_level > plafond)    → filtre soft, ignoré en exploratory
      4. Budget activité  (adult_price > plafond TND) → filtre soft, ignoré en exploratory

    Hôtels et vols ne sont pas filtrés par prix — ils n'ont pas de champ prix exploitable.
    Le ranking_node les ordonnera selon le tier (partner > catalogue) et les préférences.
    """

    def __init__(self):
        super().__init__(NodeConfig(name="constraint_validator", node_type="technical"))

    # ------------------------------------------------------------------
    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:

        candidates: List[Dict] = list(state.get("candidates") or [])

        if not candidates:
            return {"candidates": []}

        merged_context      = state.get("merged_context")      or {}
        availability_result = state.get("availability_result") or {}
        suggestion_mode     = state.get("suggestion_mode")     or "exploratory"

        budget_level   = str(merged_context.get("budget_level") or "medium").lower()
        booked_ids     = set(str(x) for x in (availability_result.get("booked_activity_ids") or []))
        is_exploratory = suggestion_mode == "exploratory"

        removed = {
            "already_booked":   0,
            "unavailable":      0,
            "budget_restaurant": 0,
            "budget_activity":  0,
        }
        kept: List[Dict] = []

        for c in candidates:
            domain = c.get("domain", "")

            # ── RÈGLE 1 : activité déjà réservée par ce voyageur ─────────────
            if domain == "activity":
                act_id = str(c.get("id") or c.get("activity_id") or "")
                if (act_id and act_id in booked_ids) or c.get("already_booked"):
                    removed["already_booked"] += 1
                    continue

            # ── RÈGLE 2 : indisponibilité confirmée par la source ─────────────
            # is_available: True=confirmé | False=indispo (capacité OU récurrence) | None=inconnu (conservé)
            if c.get("is_available") is False:
                removed["unavailable"] += 1
                continue

            # ── RÈGLE 3 : budget restaurant (soft) ───────────────────────────
            if domain == "restaurant" and not is_exploratory:
                ceiling = _BUDGET_PRICE_LEVEL.get(budget_level)
                if ceiling is not None:
                    pl = c.get("price_level")
                    if pl is not None:
                        # price_level peut être un entier (Google Places) ou une string ("$"…"$$$$")
                        pl_int = _PRICE_LEVEL_STR_TO_INT.get(str(pl).strip(), None) if isinstance(pl, str) else None
                        try:
                            pl_int = pl_int if pl_int is not None else int(pl)
                        except (ValueError, TypeError):
                            pl_int = None
                    if pl is not None and pl_int is not None and pl_int > ceiling:
                        removed["budget_restaurant"] += 1
                        continue

            # ── RÈGLE 4 : budget activité (soft) ─────────────────────────────
            if domain == "activity" and not is_exploratory:
                max_price = _BUDGET_MAX_ACTIVITY_TND.get(budget_level)
                if max_price is not None:
                    adult_price = float(c.get("adult_price") or 0.0)
                    if adult_price > 0 and adult_price > max_price:
                        removed["budget_activity"] += 1
                        continue

            kept.append(c)

        total_removed = sum(removed.values())
        self.logger.info(
            f"in={len(candidates)} out={len(kept)} removed={total_removed} "
            f"| {removed} | budget={budget_level} | exploratory={is_exploratory}"
        )

        return {"candidates": kept}
