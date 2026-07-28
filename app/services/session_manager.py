"""
SessionManager — SEUL point d'accès à la persistance de session Redis.
Aucun node LangGraph n'appelle Redis directement. Seul main.py utilise ce service.

Champs persistés :
  last_candidates        : 3-4 candidats présentés au dernier tour (pipeline informatif)
  conversation_last_turn : 2 derniers messages (follow-up)
  destination            : dernière destination connue
  last_intent            : dernier intent primaire
  suggestion_mode        : mode actuel
  weather_context        : météo (clé séparée, TTL 2h, partagée entre sessions)

Dégradation gracieuse : si Redis est down, toutes les méthodes retournent silencieusement
sans planter — le pipeline continue en mode mémoire locale.
"""
import json
import logging
from typing import Any, Dict, List, Optional

from app.config.redis_config import r
from app.config.settings import (
    SESSION_TTL_SECONDS,
    WEATHER_CACHE_TTL_SECONDS,
    SESSION_MAX_BYTES,
    SESSION_MAX_CANDIDATES,
    REDIS_ENV,
)

logger = logging.getLogger(__name__)

_CANDIDATE_FIELDS = ("name", "destination", "address", "phone", "lat", "lng", "type", "activity_type")


def _session_key(user_id: str) -> str:
    return f"session:{REDIS_ENV}:{user_id}"


def _weather_key(destination: str) -> str:
    slug = destination.lower().strip().replace(" ", "_")
    return f"weather:{REDIS_ENV}:{slug}"


def _trim_candidates(candidates: List[Dict]) -> List[Dict]:
    """Extrait uniquement les champs utiles pour le pipeline informatif."""
    result = []
    for c in (candidates or [])[:SESSION_MAX_CANDIDATES]:
        trimmed = {k: c[k] for k in _CANDIDATE_FIELDS if c.get(k) is not None}
        result.append(trimmed)
    return result


def _trim_session(data: Dict) -> Dict:
    """Réduit la taille de la session si elle dépasse SESSION_MAX_BYTES.
    Stratégie : d'abord tronquer à 2 candidats, puis tronquer les contenus à 100 chars."""
    data = dict(data)
    if "last_candidates" in data:
        data["last_candidates"] = data["last_candidates"][:2]
    for msg in data.get("conversation_last_turn") or []:
        if "content" in msg:
            msg["content"] = msg["content"][:100]
    return data


class SessionManager:

    def load(self, user_id: str) -> Dict[str, Any]:
        """Charge la session depuis Redis. Retourne {} si absente ou si Redis est down."""
        if r is None:
            return {}
        try:
            raw = r.get(_session_key(user_id))
            if raw is None:
                return {}
            return json.loads(raw)
        except Exception as e:
            logger.warning(f"[SessionManager] load échoué pour {user_id}: {e}")
            return {}

    def save(self, user_id: str, session_data: Dict[str, Any]) -> None:
        """Persiste la session dans Redis avec TTL SESSION_TTL_SECONDS.
        Ne plante jamais — log WARNING si Redis est down et continue."""
        if r is None:
            return
        try:
            clean = {k: v for k, v in session_data.items() if v is not None}
            serialized = json.dumps(clean, ensure_ascii=False)
            if len(serialized.encode("utf-8")) > SESSION_MAX_BYTES:
                logger.warning(
                    f"[SessionManager] session {user_id} dépasse {SESSION_MAX_BYTES}B — troncature"
                )
                clean = _trim_session(clean)
                serialized = json.dumps(clean, ensure_ascii=False)
            r.setex(_session_key(user_id), SESSION_TTL_SECONDS, serialized)
        except Exception as e:
            logger.warning(f"[SessionManager] save échoué pour {user_id}: {e}")

    def clear(self, user_id: str) -> None:
        """Supprime la session (déconnexion, reset)."""
        if r is None:
            return
        try:
            r.delete(_session_key(user_id))
        except Exception as e:
            logger.warning(f"[SessionManager] clear échoué pour {user_id}: {e}")

    def load_weather(self, destination: str) -> Optional[Dict[str, Any]]:
        """Charge weather_context depuis Redis (TTL 2h, clé partageable entre sessions)."""
        if r is None or not destination:
            return None
        try:
            raw = r.get(_weather_key(destination))
            if raw is None:
                return None
            return json.loads(raw)
        except Exception as e:
            logger.warning(f"[SessionManager] load_weather échoué pour {destination}: {e}")
            return None

    def save_weather(self, destination: str, weather_context: Dict[str, Any]) -> None:
        """Persiste weather_context avec TTL séparé de 2h."""
        if r is None or not destination or not weather_context:
            return
        try:
            serialized = json.dumps(weather_context, ensure_ascii=False)
            r.setex(_weather_key(destination), WEATHER_CACHE_TTL_SECONDS, serialized)
        except Exception as e:
            logger.warning(f"[SessionManager] save_weather échoué pour {destination}: {e}")
