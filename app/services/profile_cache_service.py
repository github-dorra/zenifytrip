"""
app/services/profile_cache_service.py
═══════════════════════════════════════════════════════════════════════════════
RÔLE ET INTÉRÊT
───────────────
Ce fichier est la COUCHE MONGODB DU CACHE PROFIL VOYAGEUR.

Migration 2026-07-28 : remplace Redis (profile:{traveller_id}) par MongoDB
Atlas. Redis reste réservé aux données réellement éphémères (interactions
Phase 5, sessions, cache temps réel météo/prix — cf. redis_config.py). Le
profil, avec un TTL pouvant aller jusqu'à 30 jours, correspond mieux à un
enregistrement persistant avec expiration qu'à un cache mémoire volatil —
et MongoDB Atlas est déjà une dépendance dure du projet (restaurant_collection,
activities_collection), contrairement à Redis qui peut être non configuré
(cf. redis_config.py::r peut être None).

POURQUOI CE FICHIER EXISTE :
  Sans cache → ProfileLoaderNode appelle l'API à chaque message (~1500ms).
  Avec cache → lecture MongoDB en quelques ms.

CE QU'IL STOCKE :
  Collection : traveller_profile_cache (app/config/mongodb.py)
  _id        : traveller_id — clé unique, même rôle que la clé Redis
  profile    : profil enrichi complet produit par ProfileBuilderService
  cached_at  : date d'écriture
  expires_at : calculé depuis returnDate du contrat (même logique qu'avant) :
               → Voyage futur : TTL = (returnDate - now) + 7 jours
               → Voyage passé : TTL = 7 jours
               → Maximum      : 30 jours
  Index TTL natif sur expires_at (expireAfterSeconds=0, cf. mongodb.py) —
  sweep MongoDB périodique (~60s), équivalent fonctionnel du SETEX Redis.
  Une vérification défensive de expires_at est aussi faite à la lecture,
  au cas où le sweep n'est pas encore passé.

QUAND EST-IL APPELÉ :
  1. À l'authentification → on_user_login() → build + stockage
  2. À chaque message     → get_profile()   → lecture cache

FALLBACK SI MONGODB INDISPONIBLE :
  → on_user_login() : construit le profil mais ne stocke pas → retourne quand même
  → get_profile()   : retourne None → ProfileLoaderNode appelle l'API directement
  → Le système ne crashe JAMAIS à cause du cache
"""

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from app.services.profile_builder_service import ProfileBuilderService
from app.config.settings import PROFILE_CACHE_DEFAULT_TTL_SECONDS
from app.config.mongodb import traveller_profile_collection

logger = logging.getLogger("services.profile_cache")


class ProfileCacheService:

    # Appelé à l'authentification ----------------------------------------------------

    @staticmethod
    def on_user_login(traveller_id: str, user_id: str) -> Optional[Dict[str, Any]]:
        """
        À appeler quand l'utilisateur s'authentifie.
        Force le rechargement depuis les APIs et stocke dans MongoDB.

        Args:
            traveller_id : ID voyageur (depuis state)
            user_id      : ID user connecté (depuis state) — jamais global

        Returns:
            Le profil structuré ou None si échec.
        """
        if not traveller_id or not user_id:
            logger.warning("[ProfileCache] on_user_login: paramètres manquants")
            return None

        logger.info(f"[ProfileCache] Login → build profil pour {traveller_id}")

        try:
            result = ProfileBuilderService.build(
                traveller_id=traveller_id,
                user_id=user_id,
            )

            if not result:
                logger.warning(f"[ProfileCache] Build échoué pour {traveller_id}")
                return None

            profile = result.get("profile")
            if not profile:
                logger.warning(
                    f"[ProfileCache] Empty profile for {traveller_id}"
                )
                return None

            ttl_seconds = max(60, int(result.get("ttl_seconds", PROFILE_CACHE_DEFAULT_TTL_SECONDS)))
            # Stockage MongoDB avec TTL dynamique
            ProfileCacheService._set(traveller_id, profile, ttl_seconds)

            logger.info(
                f"[ProfileCache] ✅ Profil mis en cache | "
                f"traveller_id={traveller_id} | TTL={ttl_seconds}s"
            )
            return profile

        except Exception as e:
            logger.error(f"[ProfileCache] Erreur on_user_login: {e}", exc_info=True)
            return None

    # Lecture du profil — utilisée par ProfileLoaderNode -----------------------------------
    @staticmethod
    def get_profile(traveller_id: str) -> Optional[Dict[str, Any]]:
        """
        Retourne le profil depuis MongoDB.
        CACHE HIT  → retour immédiat
        CACHE MISS → retourne None (ProfileLoaderNode appellera l'API)

        Args:
            traveller_id : ID voyageur (depuis state)
        """
        if not traveller_id:
            return None

        cached = ProfileCacheService._get(traveller_id)

        if cached is not None:
            logger.debug(f"[ProfileCache] CACHE HIT — traveller_id={traveller_id}")
            return cached

        logger.info(f"[ProfileCache] CACHE MISS — traveller_id={traveller_id}")
        return None

    # Écriture manuelle — utilisée par ProfileLoaderNode sur CACHE MISS ---------------------------

    @staticmethod
    def set_profile(
        traveller_id: str,
        profile: Dict[str, Any],
        ttl_seconds: Optional[int] = None,
    ) -> bool:
        """
        Stocke un profil dans MongoDB.
        Appelé par ProfileLoaderNode quand il reconstruit le profil après un MISS.
        """
        ttl = max(60, int(ttl_seconds or PROFILE_CACHE_DEFAULT_TTL_SECONDS))
        return ProfileCacheService._set(traveller_id, profile, ttl)

    # Invalidation-------------------------------------------------------

    @staticmethod
    def invalidate(traveller_id: str) -> bool:
        """
        Supprime le profil du cache.
        À appeler si le profil est modifié côté API (ex: mise à jour agence).
        """
        if not traveller_id:
            return False
        try:
            result = traveller_profile_collection().delete_one({"_id": traveller_id})
            logger.info(f"[ProfileCache] Invalidé — traveller_id={traveller_id}")
            return result.deleted_count > 0
        except Exception as e:
            logger.error(f"[ProfileCache] Erreur invalidate: {e}")
            return False

    # Utilitaires --------------------------------------------------------
    @staticmethod
    def is_cached(traveller_id: str) -> bool:
        """Vérifie si le profil est présent (et non expiré) dans le cache."""
        if not traveller_id:
            return False
        try:
            now = datetime.utcnow()
            doc = traveller_profile_collection().find_one(
                {"_id": traveller_id, "expires_at": {"$gt": now}},
                {"_id": 1},
            )
            return doc is not None
        except Exception:
            return False

    @staticmethod
    def ttl(traveller_id: str) -> int:
        """Retourne le TTL restant en secondes. -2 si absent/expiré (convention Redis conservée)."""
        if not traveller_id:
            return -2
        try:
            doc = traveller_profile_collection().find_one(
                {"_id": traveller_id}, {"expires_at": 1}
            )
            if not doc:
                return -2
            remaining = (doc["expires_at"] - datetime.utcnow()).total_seconds()
            return int(remaining) if remaining > 0 else -2
        except Exception:
            return -2

    # Helpers privés MongoDB -----------------------------------------------

    @staticmethod
    def _get(traveller_id: str) -> Optional[Dict[str, Any]]:
        try:
            now = datetime.utcnow()
            doc = traveller_profile_collection().find_one(
                {"_id": traveller_id, "expires_at": {"$gt": now}}
            )
            if not doc:
                return None
            return doc.get("profile")
        except Exception as e:
            logger.warning(f"[ProfileCache] Erreur lecture MongoDB: {e}")
            return None

    @staticmethod
    def _set(traveller_id: str, profile: Dict[str, Any], ttl: int) -> bool:
        if not traveller_id or not profile:
            return False
        try:
            now = datetime.utcnow()
            traveller_profile_collection().update_one(
                {"_id": traveller_id},
                {"$set": {
                    "profile": profile,
                    "cached_at": now,
                    "expires_at": now + timedelta(seconds=ttl),
                }},
                upsert=True,
            )
            return True
        except Exception as e:
            logger.warning(f"[ProfileCache] Erreur écriture MongoDB: {e}")
            return False
