"""
Centralized cache for the ZenifyTrip system.
- In-memory with TTL (fast reads)
- JSON file persistence (survives restarts)
- TTL constants per service domain
"""

import os
import json
import time
import threading
from typing import Any, Callable, Dict, Optional

CACHE_FILE = os.path.join(os.path.dirname(__file__), "..", ".cache", "zenifytrip_cache.json")


class SimpleTTLCache:

    # =========================================================
    # TTL CONSTANTS — secondes
    # =========================================================
    TTL_HOTELS         = 86400   # 24h — catalogue stable
    TTL_HOTEL_SERVICES = 7200    # 2h  — services agence mis à jour fréquemment
    TTL_ZONES          = 86400   # 24h
    TTL_WEATHER        = 7200    # 2h
    TTL_MAPS           = 43200   # 12h
    TTL_ACTIVITIES     = 86400   # 24h
    TTL_PROFILE        = 3600    # 1h
    TTL_FLIGHTS        = 21600   # 6h  — liste vols (change peu dans la journée)
    TTL_AIRLINES       = 86400   # 24h — compagnies aériennes (très stable)
    TTL_AIRPORTS       = 86400   # 24h — aéroports (très stable)
    TTL_RESTAURANTS    = 259200  # 72h — restaurants (stable, données Google Places / Tavily)

    def __init__(self):
        self._store: Dict[str, dict] = {}
        self._save_lock = threading.Lock()
        self._load_from_file()

    # =========================================================
    # PUBLIC API — inchangée pour rétrocompatibilité
    # =========================================================

    def get(self, key: str) -> Optional[Any]:
        item = self._store.get(key)
        if item is None:
            return None

        if time.time() > item["expires_at"]:
            self._store.pop(key, None)
            return None

        return item["value"]

    def set(self, key: str, value: Any, ttl_seconds: int) -> None:
        self._store[key] = {
            "value":      value,
            "expires_at": time.time() + ttl_seconds,
        }
        self._save_to_file_async()

    def delete(self, key: str) -> None:
        self._store.pop(key, None)
        self._save_to_file_async()

    # =========================================================
    # HELPERS
    # =========================================================

    def get_or_set(self, key: str, loader: Callable[[], Any], ttl_seconds: int) -> Any:
        """
        Retourne la valeur depuis le cache si présente et valide.
        Sinon appelle loader(), stocke le résultat et le retourne.

        Usage :
            data = cache.get_or_set("flights_all", FlightService.get_flights, TTL_FLIGHTS)
        """
        cached = self.get(key)
        if cached is not None:
            return cached
        value = loader()
        if value is not None:
            self.set(key, value, ttl_seconds)
        return value

    def invalidate_prefix(self, prefix: str) -> int:
        """
        Supprime toutes les entrées dont la clé commence par prefix.
        Retourne le nombre d'entrées supprimées.

        Usage :
            cache.invalidate_prefix("flights_")  # invalide tout le cache vols
        """
        keys_to_delete = [k for k in self._store if k.startswith(prefix)]
        for k in keys_to_delete:
            self._store.pop(k, None)
        if keys_to_delete:
            self._save_to_file_async()
        return len(keys_to_delete)

    def clear_expired(self) -> int:
        """Purge les entrées expirées. Retourne le nombre supprimées."""
        now = time.time()
        expired = [k for k, v in self._store.items() if v.get("expires_at", 0) <= now]
        for k in expired:
            self._store.pop(k, None)
        if expired:
            self._save_to_file_async()
        return len(expired)

    def stats(self) -> Dict[str, Any]:
        """Retourne des métriques sur l'état du cache (debug)."""
        now = time.time()
        active = sum(1 for v in self._store.values() if v.get("expires_at", 0) > now)
        expired = len(self._store) - active
        return {
            "total_keys": len(self._store),
            "active_keys": active,
            "expired_keys": expired,
        }

    # =========================================================
    # FILE PERSISTENCE
    # =========================================================

    def _load_from_file(self) -> None:
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            now = time.time()
            for key, item in data.items():
                if isinstance(item, dict) and item.get("expires_at", 0) > now:
                    self._store[key] = item
        except (FileNotFoundError, json.JSONDecodeError):
            pass
        except Exception as e:
            print(f"[CacheService] load error: {e}")

    def _save_to_file(self) -> None:
        try:
            cache_dir = os.path.dirname(CACHE_FILE)
            os.makedirs(cache_dir, exist_ok=True)
            with open(CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump(self._store, f, ensure_ascii=False)
        except Exception as e:
            print(f"[CacheService] save error: {e}")

    def _save_to_file_async(self) -> None:
        """Écrit le cache sur disque dans un thread daemon — non bloquant."""
        snapshot = {k: v.copy() for k, v in self._store.items()}

        def _write():
            if not self._save_lock.acquire(blocking=False):
                return  # écriture déjà en cours — on saute
            try:
                cache_dir = os.path.dirname(CACHE_FILE)
                os.makedirs(cache_dir, exist_ok=True)
                with open(CACHE_FILE, "w", encoding="utf-8") as f:
                    json.dump(snapshot, f, ensure_ascii=False)
            except Exception as e:
                print(f"[CacheService] async save error: {e}")
            finally:
                self._save_lock.release()

        threading.Thread(target=_write, daemon=True).start()


cache = SimpleTTLCache()
