"""
app/services/profile_cache_service.py
═══════════════════════════════════════════════════════════════════════════════
RÔLE ET INTÉRÊT
───────────────
Ce fichier est la COUCHE REDIS du profil voyageur.

POURQUOI CE FICHIER EXISTE :
  Sans cache → ProfileLoaderNode appelle l'API à chaque message (~1500ms).
  Avec cache → lecture Redis en ~1ms. Gain x1500 par message.

  Sur une conversation de 10 messages → 15 secondes économisées.
  Sur 100 utilisateurs simultanés → économie massive d'appels API.

CE QU'IL STOCKE DANS REDIS :
  Clé    : "profile:{traveller_id}"
  Valeur : profil enrichi complet produit par ProfileBuilderService
  TTL    : dynamique calculé depuis returnDate du contrat :
           → Voyage futur : TTL = (returnDate - now) + 7 jours
           → Voyage passé : TTL = 7 jours
           → Maximum      : 30 jours

QUAND EST-IL APPELÉ :
  1. À l'authentification → on_user_login() → build + stockage
  2. À chaque message     → get_profile()   → lecture instantanée

FALLBACK SI REDIS INDISPONIBLE :
  → on_user_login() : construit le profil mais ne stocke pas → retourne quand même
  → get_profile()   : retourne None → ProfileLoaderNode appelle l'API directement
  → Le système ne crashe JAMAIS à cause de Redis
"""

import json
import logging
from typing import Any, Dict, Optional

from app.services.profile_builder_service import ProfileBuilderService
from app.config.settings import ( PROFILE_CACHE_DEFAULT_TTL_SECONDS, PROFILE_CACHE_PREFIX)

from app.config.redis_config import r
from redis.exceptions import RedisError

logger = logging.getLogger("services.profile_cache")



def _make_key(traveller_id: str) -> str:
    return f"{PROFILE_CACHE_PREFIX}:{traveller_id}"



class ProfileCacheService:

   
    # Appelé à l'authentification ----------------------------------------------------
   
    @staticmethod
    def on_user_login(traveller_id: str, user_id: str) -> Optional[Dict[str, Any]]:
        """
        À appeler quand l'utilisateur s'authentifie.
        Force le rechargement depuis les APIs et stocke dans Redis.

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

            ttl_seconds = max( 60, int( result.get("ttl_seconds", PROFILE_CACHE_DEFAULT_TTL_SECONDS,)),)
            # Stockage Redis avec TTL dynamique
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
        Retourne le profil depuis Redis.
        CACHE HIT  → retour immédiat (~1ms)
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
        Stocke un profil dans Redis.
        Appelé par ProfileLoaderNode quand il reconstruit le profil après un MISS.
        """
        ttl = max( 60, int( ttl_seconds or PROFILE_CACHE_DEFAULT_TTL_SECONDS,))
        return ProfileCacheService._set(traveller_id, profile, ttl)

    
    
    # Invalidation-------------------------------------------------------

    @staticmethod
    def invalidate(traveller_id: str) -> bool:
        """
        Supprime le profil du cache.
        À appeler si le profil est modifié côté API (ex: mise à jour agence).
        """
        if not traveller_id  or not r:
            return False
        try:
            deleted = r.delete(_make_key(traveller_id))
            logger.info(f"[ProfileCache] Invalidé — traveller_id={traveller_id}")
            return bool(deleted)
        except Exception as e:
            logger.error(f"[ProfileCache] Erreur invalidate: {e}")
            return False


    # Utilitaires --------------------------------------------------------
    @staticmethod
    def is_cached(traveller_id: str) -> bool:
        """Vérifie si le profil est présent dans Redis."""
        if not traveller_id  or not r:
            return False
        try:
            return bool(r.exists(_make_key(traveller_id)))
        except Exception:
            return False

    @staticmethod
    def ttl(traveller_id: str) -> int:
        """Retourne le TTL restant en secondes."""
        if not traveller_id or not r:
            return -2
        try:
            return r.ttl(_make_key(traveller_id))
        except Exception:
            return -2


    # Helpers privés Redis -----------------------------------------------

    @staticmethod
    def _get(traveller_id: str) -> Optional[Dict[str, Any]]:
        if not traveller_id or not r:
            return None
        try:
            data = r.get(_make_key(traveller_id))
            if data is None:
                return None
            return json.loads(data)
        except (RedisError, json.JSONDecodeError) as e:
            logger.warning(f"[ProfileCache] Erreur lecture Redis: {e}")
            return None

    @staticmethod
    def _set(traveller_id: str, profile: Dict[str, Any], ttl: int) -> bool:
        if not traveller_id or not profile or not r:
            return False

        try:
            data = json.dumps(profile, ensure_ascii=False, default=str)
            r.setex(
                name=_make_key(traveller_id),
                time=ttl,
                value=data,
            )
            return True
        except (RedisError, TypeError) as e:
            logger.warning(f"[ProfileCache] Erreur écriture Redis: {e}")
            return False