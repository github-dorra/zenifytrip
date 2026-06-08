"""
Restaurant Service — Production (Approche A retenue)

Décision architecturale (2026-06-08) :
  Approche A — Google Places API pur, zéro hallucination, TTL 72h.
  Benchmark : 6/6 PASS | avg 10 candidats | ~1.4s | $0 | 0% hallucination.

Les fichiers restaurant_service_a / _b / _c restent disponibles pour référence.
"""

from app.services.restaurant_service_a import RestaurantServiceA


class RestaurantService(RestaurantServiceA):
    """Point d'entrée production — alias de RestaurantServiceA."""
    pass
