"""Redis client — connexion optionnelle avec fallback gracieux si non configuré."""
import logging
from app.config.settings import REDIS_HOST, REDIS_PORT, REDIS_USERNAME, REDIS_PASSWORD, REDIS_MAX_CONNECTIONS

import redis

_logger = logging.getLogger("config.redis")

r = None
try:
    if REDIS_HOST and REDIS_PORT:
        _pool = redis.ConnectionPool(
            host=REDIS_HOST,
            port=int(REDIS_PORT),
            decode_responses=True,
            username=REDIS_USERNAME,
            password=REDIS_PASSWORD,
            max_connections=REDIS_MAX_CONNECTIONS,  # réglé dans settings.py — varie selon plan Redis
            socket_connect_timeout=3,               # délai max pour ouvrir la connexion TCP
            socket_timeout=2,                       # délai max pour recevoir une réponse Redis
        )
        r = redis.Redis(connection_pool=_pool)
        r.ping()
        _logger.info("[Redis] Connexion OK")
    else:
        _logger.warning("[Redis] REDIS_HOST/PORT non configurés — cache Redis désactivé")
except Exception as e:
    _logger.warning(f"[Redis] Connexion échouée — cache Redis désactivé: {e}")
    r = None
