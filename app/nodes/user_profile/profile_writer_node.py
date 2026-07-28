"""
profile_writer_node.py — Phase 5

Persiste les signaux de feedback cross-session dans Redis.
Clé : interactions:{traveller_id}  |  TTL : 90 jours (INTERACTIONS_REDIS_TTL_SECONDS)

Les rejets accumulés sont lus par ranking_node au tour suivant pour exclure
les types rejetés sans nouveau signal utilisateur.

Dégradation gracieuse : si Redis est down ou traveller_id absent → no-op silencieux.
"""
import json
import logging
from typing import Any, Dict

from app.nodes.core.Base_node import BaseNode, NodeConfig
from app.config.settings import (
    INTERACTIONS_REDIS_PREFIX,
    INTERACTIONS_REDIS_TTL_SECONDS,
)

try:
    from app.config.redis_config import r as _redis
except Exception:
    _redis = None

_logger = logging.getLogger("nodes.profile_writer")


class ProfileWriterNode(BaseNode):

    def __init__(self):
        super().__init__(NodeConfig(name="profile_writer", node_type="technical"))

    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:

        feedback = state.get("feedback_event") or {}
        traveller_id = feedback.get("traveller_id")

        if not traveller_id or not _redis:
            return {"profile_written": False}

        key = f"{INTERACTIONS_REDIS_PREFIX}{traveller_id}"

        try:
            # Lire les signaux cross-session existants
            raw = _redis.get(key)
            existing = json.loads(raw) if raw else {"rejected_types": [], "liked_types": []}

            # Fusionner — le rejet prime toujours sur le like
            rejected = set(existing.get("rejected_types", [])) | set(feedback.get("rejected_types", []))
            liked    = set(existing.get("liked_types", []))    | set(feedback.get("liked_types", []))
            liked   -= rejected

            merged = {
                "rejected_types": sorted(rejected),
                "liked_types":    sorted(liked),
            }

            _redis.set(key, json.dumps(merged), ex=INTERACTIONS_REDIS_TTL_SECONDS)

            _logger.info(
                f"[ProfileWriter] interactions:{traveller_id} écrites | "
                f"rejected={merged['rejected_types']} liked={merged['liked_types']}"
            )
            return {"profile_written": True}

        except Exception as e:
            _logger.warning(f"[ProfileWriter] Redis write failed (dégradation gracieuse): {e}")
            return {"profile_written": False}
