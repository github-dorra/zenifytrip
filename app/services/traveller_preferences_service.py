"""
app/services/traveller_preferences_service.py
═══════════════════════════════════════════════════════════════════════════════
RÔLE ET INTÉRÊT
───────────────
Préférences d'onboarding — traits STABLES du voyageur (type de voyage, but du
séjour, goûts culinaires), capturées une fois via un quiz de première
utilisation (frontend/app — hors périmètre de ce service) et persistées SANS
expiration dans MongoDB (collection `traveller_preferences`).

DIFFÉRENCE AVEC profile_cache_service.py :
  traveller_profile_cache = CACHE TTL de données AGENCE (reconstructible via
                             ProfileBuilderService, expire, USER RÉEL uniquement)
  traveller_preferences   = donnée ZENIFYTRIP PROPRE, durable, jamais expirée,
                             perdue si supprimée (pas reconstructible), keyée
                             sur user_id (USER RÉEL **et** USER NATIF)

CE QU'IL STOCKE :
  _id                : user_id
  trip_type          : "solo" | "couple" | "famille" | "groupe" | null
  travel_purpose     : liste libre (ex. "détente", "découverte_culturelle")
  culinary_interests : liste libre (ex. "fruits_de_mer", "cuisine_locale")
  completed_at       : datetime | null (null si explicitement skippé)
  skipped            : bool
  updated_at         : datetime

CONSOMMÉ PAR : profile_loader_node.py (lecture) → context_merger_node.py
  (fusion travel_purpose/culinary_interests dans merged["interests"], trip_type
  dans merged["travel_persona"])

ÉCRIT PAR : set_preferences()/mark_skipped() — appelés par le futur quiz
  d'onboarding (frontend/API, hors périmètre de ce repo backend), pas par le
  graphe LangGraph lui-même.

FALLBACK SI MONGODB INDISPONIBLE :
  Toutes les méthodes retournent None/False proprement — le système ne
  crashe JAMAIS à cause de ce service (même doctrine que profile_cache_service.py).
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from app.config.mongodb import traveller_preferences_collection

logger = logging.getLogger("services.traveller_preferences")

TRIP_TYPES = {"solo", "couple", "famille", "groupe"}


class TravellerPreferencesService:

    @staticmethod
    def get_preferences(user_id: Optional[str]) -> Optional[Dict[str, Any]]:
        """
        Retourne {trip_type, travel_purpose, culinary_interests} ou None si
        aucune préférence capturée, ou si l'utilisateur a explicitement skippé
        le quiz (skip = pas de donnée à fusionner, pas une valeur vide à traiter).
        """
        if not user_id:
            return None
        try:
            doc = traveller_preferences_collection().find_one({"_id": user_id})
            if not doc or doc.get("skipped"):
                return None
            return {
                "trip_type":          doc.get("trip_type"),
                "travel_purpose":     doc.get("travel_purpose") or [],
                "culinary_interests": doc.get("culinary_interests") or [],
            }
        except Exception as e:
            logger.warning(f"[TravellerPreferences] get_preferences error: {e}")
            return None

    @staticmethod
    def set_preferences(
        user_id: str,
        trip_type: Optional[str] = None,
        travel_purpose: Optional[List[str]] = None,
        culinary_interests: Optional[List[str]] = None,
    ) -> bool:
        """Écrit/met à jour les préférences. Appelé par le quiz d'onboarding (hors ce repo)."""
        if not user_id:
            return False
        if trip_type and trip_type not in TRIP_TYPES:
            logger.warning(f"[TravellerPreferences] trip_type inconnu ignoré: {trip_type!r}")
            trip_type = None
        try:
            now = datetime.utcnow()
            traveller_preferences_collection().update_one(
                {"_id": user_id},
                {"$set": {
                    "trip_type":          trip_type,
                    "travel_purpose":     travel_purpose or [],
                    "culinary_interests": culinary_interests or [],
                    "completed_at":       now,
                    "skipped":            False,
                    "updated_at":         now,
                }},
                upsert=True,
            )
            return True
        except Exception as e:
            logger.warning(f"[TravellerPreferences] set_preferences error: {e}")
            return False

    @staticmethod
    def mark_skipped(user_id: str) -> bool:
        """Enregistre que l'utilisateur a explicitement passé le quiz — ne plus le reproposer."""
        if not user_id:
            return False
        try:
            now = datetime.utcnow()
            traveller_preferences_collection().update_one(
                {"_id": user_id},
                {
                    "$set": {"skipped": True, "updated_at": now},
                    "$setOnInsert": {"completed_at": None},
                },
                upsert=True,
            )
            return True
        except Exception as e:
            logger.warning(f"[TravellerPreferences] mark_skipped error: {e}")
            return False

    @staticmethod
    def has_completed_onboarding(user_id: str) -> bool:
        """
        True si un document existe déjà (complété OU skippé) — dans les deux cas,
        le frontend ne doit plus proposer le quiz automatiquement.
        """
        if not user_id:
            return False
        try:
            return traveller_preferences_collection().count_documents({"_id": user_id}) > 0
        except Exception as e:
            logger.warning(f"[TravellerPreferences] has_completed_onboarding error: {e}")
            return False
