"""
Scoring partagé entre les sources d'activités (SOURCE 1 interne + SOURCE 2 MongoDB).
Une seule implémentation par règle — jamais dupliquée dans les services.
"""

# Poids max de la composante budget dans user_score — aligné sur les autres
# composantes des services (keyword 0.35 / dispo|rating 0.25 / budget 0.20 / traveler_type 0.20)
BUDGET_COMPONENT_MAX = 0.20


def budget_proximity_score(price: float, budget_level: str, ranges: dict) -> float:
    """
    Score budget continu 0.0 → BUDGET_COMPONENT_MAX (remplace le binaire V1).
      - prix dans la fourchette [lo, hi]    → score plein
      - prix au-dessus de hi                → décroissance linéaire, nul à 2×hi
      - prix en-dessous de lo (ex. luxury)  → décroissance linéaire, nul à 0
    Exemples (medium, hi=200 TND) : 180→0.20 | 250→0.15 | 300→0.10 | 400+→0.0
    """
    lo, hi = ranges.get(budget_level, (0.0, float("inf")))

    if lo <= price <= hi:
        return BUDGET_COMPONENT_MAX
    if price > hi:
        return round(BUDGET_COMPONENT_MAX * max(0.0, 1 - (price - hi) / hi), 4)
    # price < lo — pertinent uniquement si la fourchette a un plancher (luxury/premium)
    return round(BUDGET_COMPONENT_MAX * max(0.0, 1 - (lo - price) / lo), 4) if lo > 0 else BUDGET_COMPONENT_MAX
