"""Utilitaires temps partagés — une seule implémentation pour tout le projet."""
from datetime import datetime
from typing import Any


def hour_of(iso_time: Any) -> int:
    """Heure (0-23) d'un timestamp ISO — -1 si absent/illisible (jamais bloquant)."""
    if not iso_time:
        return -1
    try:
        return datetime.fromisoformat(str(iso_time).replace("Z", "+00:00")).hour
    except (ValueError, TypeError):
        return -1
